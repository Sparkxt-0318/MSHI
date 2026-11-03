"""Single entry point for the v3 pipeline.

    python -m mshi.run --stage all                 # every stage, in order
    python -m mshi.run --stage build_sites         # one stage (uses existing outputs of its inputs)
    python -m mshi.run --list                      # stages and dependencies
    python -m mshi.run --stage all --smoke         # 50-site smoke run in data/interim/smoke/

Requested stages always run in pipeline order, whatever the order on the command line. Statuses in
results/run_log.jsonl: ``ok``; ``blocked`` (the egress proxy refused a pinned source: a network-policy
block); ``unavailable`` (a source could not be reached); ``stale`` (an input result is missing, from
another config or code, or its files changed after it was written: re-run the upstream stages, e.g.
``make all``; also used by ``repro_checks`` when a row is STALE); ``skipped`` (an upstream stage in this
invocation did not complete, or the reproduction gate is closed; dependants are never mocked); ``error``.
Exit code: 0 all ok; 1 any error (including a reproduction target outside tolerance); 2 no error, but
some stage was blocked, unavailable, stale or skipped.

Results are stamped with the config and code hashes taken when the run started (``Config.invocation``),
so a result never claims code that was edited while the stage ran.

Reproduction gate ("reproduce before you extend"): a stage ordered after ``repro_checks`` (later phases)
runs only if results/reproduction_check.json is current (its inputs included, mshi.io.result_staleness) and
every target row the stage builds on was compared and is within tolerance: no FAIL, STALE or NOT RUN row in
the row groups the stage ``needs`` (``site_build``: COSORE and site-build counts; ``locked_test``: the locked
test and its re-runs; ``npp``: the NPP check). A stage that uses gridded features needs all three; one that
uses only the site records needs ``site_build``. A DEVIATION (a locked-test re-run that differs from the
locked result) is reported but does not close the gate. If ``repro_checks`` is part of the invocation it must
also have finished ``ok``. Smoke runs do not apply the gate: their outputs (data/interim/smoke/) are not
results, and they never run ``repro_checks``.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .config import Config, load_config
from .io import StaleInputError, read_table, require_current, require_outputs, write_json, write_result, write_table
from .netutil import SourceUnavailableError
from .runlog import git_commit, package_versions, provenance, stage_timer

log = logging.getLogger("mshi")

GATE = "repro_checks"      # stages ordered after it need a passing reproduction table (module docstring)
ROW_GROUPS = ("site_build", "locked_test", "npp")      # reproduction-row groups (mshi.analysis.repro_checks)


@dataclass
class Stage:
    name: str
    func: Callable[[Config], dict]
    deps: list[str] = field(default_factory=list)
    doc: str = ""
    needs: tuple[str, ...] = ROW_GROUPS      # reproduction-row groups a stage after the gate builds on


def _stages() -> list[Stage]:
    from .analysis.clean_test import clean_test
    from .analysis.repro_checks import repro_checks
    from .analysis.site_diagnostics import site_diagnostics
    from .data.cosore import cosore_annual, cosore_annual_analysis
    from .data.features import features
    from .data.sites_analysis import build_sites_analysis
    from .data.fetch import fetch_cosore, fetch_naturalearth, fetch_srdb
    from .data.modis import modis_points
    from .data.rasters import fetch_soilgrids, fetch_worldclim
    from .data.sites import build_sites
    return [
        Stage("fetch_srdb", fetch_srdb, [], "SRDB v5 CSV at the pinned commit (SHA-256 verified)"),
        Stage("fetch_cosore", fetch_cosore, [], "COSORE v0.8.0 shallow checkout at the pinned commit"),
        Stage("fetch_naturalearth", fetch_naturalearth, [], "Natural Earth v5.1.2 GeoJSON (SHA-256 verified)"),
        Stage("cosore_annual", cosore_annual, ["fetch_cosore"], "COSORE -> annual Rs per site"),
        Stage("cosore_annual_analysis", cosore_annual_analysis, ["fetch_cosore"],
              "COSORE for v3 analyses: untreated Rs ports, full-year coverage (Q-6)"),
        Stage("build_sites", build_sites, ["fetch_srdb", "cosore_annual", "fetch_naturalearth"],
              "records, QC flags, coordinate check, 5-km sites, continents"),
        Stage("site_diagnostics", site_diagnostics, ["build_sites"],
              "exploratory: Mercator vs true distance in the coordinate check, 5-km chaining"),
        Stage("build_sites_analysis", build_sites_analysis,
              ["fetch_srdb", "cosore_annual_analysis", "fetch_naturalearth", "build_sites"],
              "site tables for v3 analyses: geodesic distances, geographic continent (Q-2, Q-5, Q-6)"),
        Stage("smoke_subset", smoke_subset, ["build_sites", "build_sites_analysis"],
              "(smoke runs only) keep a 50-site subset"),
        Stage("fetch_worldclim", fetch_worldclim, [], "WorldClim 2.1 bioclim 2.5'"),
        Stage("fetch_soilgrids", fetch_soilgrids, [], "SoilGrids 2.0 5-15 cm mean, 0.05 deg WCS"),
        Stage("modis_points", modis_points, ["build_sites", "build_sites_analysis"],
              "MODIS NPP/LST window means (Planetary Computer)"),
        Stage("features", features, ["build_sites", "fetch_worldclim", "fetch_soilgrids", "modis_points"],
              "attach WorldClim, SoilGrids, MODIS to sites"),
        Stage("clean_test", clean_test, ["features"], "locked Asia -> Europe test (hash-verified re-run)"),
        Stage("repro_checks", repro_checks, [], "compare outputs with the handoff reproduction targets"),
    ]


SITE_TABLES = ("records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet")
ANALYSIS_TABLES = ("records_analysis.parquet", "sites_analysis_qc.parquet", "sites_analysis_repo.parquet")


def smoke_subset(cfg: Config) -> dict:
    """Smoke runs only: reduce the site tables (locked and analysis builds) to a seeded subset of
    ``smoke.n_sites`` sites each. The sandbox's build results are re-recorded with the subset tables as their
    outputs, so later stages accept them as current inputs."""
    if cfg.out_root is None:
        return {"skipped": "not a smoke run"}
    n, seed = cfg["smoke"]["n_sites"], cfg["smoke"]["seed"]
    out, names = {}, []
    for result, files, prefix in [("build_sites.json", SITE_TABLES, "sites_v3"),
                                  ("build_sites_analysis.json", ANALYSIS_TABLES, "sites_analysis")]:
        tables = [cfg.path("derived", f) for f in files]
        b = require_outputs(cfg, result, tables)
        ins = dict(b.get("_inputs") or {})      # the re-recorded build keeps the inputs of the full build
        sub_out = {}
        for tag in cfg["site_build"]["variants"]:
            p = cfg.path("derived", f"{prefix}_{tag}.parquet")
            st = read_table(cfg, p)
            idx = np.sort(np.random.default_rng(seed).choice(len(st), size=min(n, len(st)), replace=False))
            sub = st.iloc[idx].reset_index(drop=True)
            write_table(sub, p)
            sub_out[tag] = {"n": int(len(sub)), "by_continent": sub.continent.value_counts().to_dict()}
        write_result(cfg, {**b, "smoke_subset": sub_out}, result, outputs=tables, inputs=ins)
        require_current(cfg, result)            # registers the re-recorded result as read
        out[prefix], names = sub_out, names + [result]
    subset_tables = [cfg.path("derived", f) for f in SITE_TABLES[1:] + ANALYSIS_TABLES[1:]]
    write_result(cfg, out, "smoke_subset.json", outputs=subset_tables, inputs=names)
    return out


def _gate_status(cfg: Config, status: dict[str, str], names: list[str], needs: tuple[str, ...] = ROW_GROUPS) -> str:
    """'ok' if the reproduction gate is open for a stage that ``needs`` these row groups (module docstring),
    else the reason it is closed."""
    if GATE in names and status.get(GATE) != "ok":
        return status.get(GATE, "not run")
    try:
        rc = require_current(cfg, "reproduction_check.json")
    except StaleInputError as e:
        return f"stale: {e}"
    if set(needs) >= set(ROW_GROUPS):
        summary = rc.get("summary") or {}
    else:                  # only the rows the stage builds on; a row without a group counts for every stage
        rows = [r for r in rc.get("rows") or [] if "group" not in r or r["group"] in needs]
        summary = {k: sum(r.get("status") == k for r in rows) for k in ("PASS", "FAIL", "STALE", "NOT RUN")}
    bad = {k: summary.get(k, 0) for k in ("FAIL", "STALE", "NOT RUN") if summary.get(k, 0)}
    if not summary.get("PASS"):
        bad["PASS"] = summary.get("PASS", 0)
    where = "" if set(needs) >= set(ROW_GROUPS) else f" in the {'/'.join(needs)} rows"
    return f"results/reproduction_check.json has {bad}{where}" if bad else "ok"


def run(stage_names: list[str], cfg: Config, full: bool = False) -> int:
    """Run ``stage_names`` in pipeline order; see the module docstring for statuses and exit codes."""
    all_stages = _stages()          # imports every stage module before the code hash is taken
    order = [s.name for s in all_stages]
    stages = {s.name: s for s in all_stages}
    names = sorted(dict.fromkeys(stage_names), key=order.index)
    smoke = cfg.out_root is not None
    log_path = cfg.path("results", "run_log.jsonl")
    commit = git_commit(cfg.repo_root)
    snapshot = provenance(cfg)
    prov = {"git_commit": commit, **snapshot, "invocation": ["all"] if full else names, "smoke": smoke}
    if full:   # the environment record describes the last full run (stage results carry their own provenance)
        write_json({"git_commit": commit, **snapshot, "versions": package_versions()},
                   cfg.path("results", "environment.json"))
    status: dict[str, str] = {}
    cfg.invocation = {"stages": names, "status": status, "provenance": snapshot}
    errors = False
    try:
        for name in names:
            st = stages[name]
            if name == "smoke_subset" and not smoke:
                continue
            if smoke and name in ("clean_test", "repro_checks", "site_diagnostics"):
                log.info("%-18s not part of smoke runs (locked test and targets need the full site set)", name)
                continue
            absent = [d for d in st.deps if d not in names]
            if absent and not full:
                log.info("%-18s uses existing outputs of %s (not requested; checked for currency)", name,
                         ", ".join(absent))
            up = [d for d in st.deps if d in status and status[d] != "ok"]
            msg = f"skipped: upstream {', '.join(up)} not available" if up else None
            if msg is None and GATE in order and order.index(name) > order.index(GATE):
                if smoke:
                    log.info("%-18s smoke run: reproduction gate not applied (smoke outputs are not results)", name)
                else:
                    gate = _gate_status(cfg, status, names, st.needs)
                    msg = None if gate == "ok" else f"skipped: reproduction gate closed ({GATE}: {gate})"
            if msg:
                with stage_timer(log_path, name, prov) as rec:
                    rec["status_override"] = msg
                status[name] = msg
                log.warning("%-18s %s", name, msg)
                continue
            log.info("%-18s start", name)
            try:
                with stage_timer(log_path, name, prov) as rec:
                    try:
                        rec["result"] = st.func(cfg)
                    except SourceUnavailableError as e:
                        rec["status_override"] = f"{'blocked' if e.kind == 'proxy_denied' else 'unavailable'}: {e}"
                    except StaleInputError as e:
                        rec["status_override"] = f"stale: {e}"
                status[name] = rec["status"]
                log.info("%-18s %s (%.1fs)", name, status[name].split(":")[0].upper(), rec["seconds"])
            except Exception as e:  # noqa: BLE001 - record and continue with independent stages
                status[name] = f"error: {type(e).__name__}: {e}"
                errors = True
                log.exception("%s failed", name)
    finally:
        cfg.invocation.pop("provenance", None)       # later direct calls stamp their own provenance
    not_ok = {k: v for k, v in status.items() if v != "ok"}
    if not_ok:
        log.warning("stages not completed: %s", not_ok)
    return 1 if errors else (2 if not_ok else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mshi.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", action="append", help="stage name or 'all' (repeatable)")
    ap.add_argument("--config", default=None, help="config file (default configs/v3.yaml)")
    ap.add_argument("--smoke", action="store_true", help="50-site smoke run into data/interim/smoke/")
    ap.add_argument("--list", action="store_true", help="list stages")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    names = [s.name for s in _stages()]
    if a.list or not a.stage:
        for s in _stages():
            print(f"{s.name:20s} deps={','.join(s.deps) or '-':45s} {s.doc}")
        return 0
    full = "all" in a.stage
    want = names if full else a.stage
    bad = [s for s in want if s not in names]
    if bad:
        ap.error(f"unknown stage(s): {bad}; choose from {names}")
    cfg = load_config(a.config)
    if a.smoke:
        cfg = load_config(a.config, out_root=cfg.path("interim", "smoke"))
    return run(want, cfg, full=full)


if __name__ == "__main__":
    sys.exit(main())
