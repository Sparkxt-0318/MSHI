"""Single entry point for the v3 pipeline.

    python -m mshi.run --stage all                 # every stage, in order
    python -m mshi.run --stage build_sites         # one stage (inputs must exist)
    python -m mshi.run --list                      # stages and dependencies
    python -m mshi.run --stage all --smoke         # 50-site smoke run in data/interim/smoke/

A stage whose pinned source cannot be reached is recorded as ``blocked`` in results/run_log.jsonl;
with ``--stage all`` the stages that depend on it are skipped (never mocked) and the run exits 2.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .config import Config, load_config
from .io import read_table, write_json, write_table
from .netutil import SourceUnavailableError
from .runlog import git_commit, package_versions, stage_timer

log = logging.getLogger("mshi")


@dataclass
class Stage:
    name: str
    func: Callable[[Config], dict]
    deps: list[str] = field(default_factory=list)
    doc: str = ""


def _stages() -> list[Stage]:
    from .analysis.clean_test import clean_test
    from .analysis.repro_checks import repro_checks
    from .analysis.site_diagnostics import site_diagnostics
    from .data.cosore import cosore_annual
    from .data.features import features
    from .data.fetch import fetch_cosore, fetch_naturalearth, fetch_srdb
    from .data.modis import modis_points
    from .data.rasters import fetch_soilgrids, fetch_worldclim
    from .data.sites import build_sites
    return [
        Stage("fetch_srdb", fetch_srdb, [], "SRDB v5 CSV at the pinned commit (SHA-256 verified)"),
        Stage("fetch_cosore", fetch_cosore, [], "COSORE v0.8.0 shallow checkout at the pinned commit"),
        Stage("fetch_naturalearth", fetch_naturalearth, [], "Natural Earth v5.1.2 GeoJSON (SHA-256 verified)"),
        Stage("cosore_annual", cosore_annual, ["fetch_cosore"], "COSORE -> annual Rs per site"),
        Stage("build_sites", build_sites, ["fetch_srdb", "cosore_annual", "fetch_naturalearth"],
              "records, QC flags, coordinate check, 5-km sites, continents"),
        Stage("site_diagnostics", site_diagnostics, ["build_sites"],
              "exploratory: Mercator vs true distance in the coordinate check, 5-km chaining"),
        Stage("smoke_subset", smoke_subset, ["build_sites"], "(smoke runs only) keep a 50-site subset"),
        Stage("fetch_worldclim", fetch_worldclim, [], "WorldClim 2.1 bioclim 2.5'"),
        Stage("fetch_soilgrids", fetch_soilgrids, [], "SoilGrids 2.0 5-15 cm mean, 0.05 deg WCS"),
        Stage("modis_points", modis_points, ["build_sites"], "MODIS NPP/LST window means (Planetary Computer)"),
        Stage("features", features, ["build_sites", "fetch_worldclim", "fetch_soilgrids", "modis_points"],
              "attach WorldClim, SoilGrids, MODIS to sites"),
        Stage("clean_test", clean_test, ["features"], "locked Asia -> Europe test (hash-verified re-run)"),
        Stage("repro_checks", repro_checks, [], "compare outputs with the handoff reproduction targets"),
    ]


def smoke_subset(cfg: Config) -> dict:
    """Smoke runs only: reduce both site tables to a seeded subset of ``smoke.n_sites`` sites."""
    if cfg.out_root is None:
        return {"skipped": "not a smoke run"}
    n, seed = cfg["smoke"]["n_sites"], cfg["smoke"]["seed"]
    out = {}
    for tag in cfg["site_build"]["variants"]:
        p = cfg.path("derived", f"sites_v3_{tag}.parquet")
        st = read_table(cfg, p)
        idx = np.sort(np.random.default_rng(seed).choice(len(st), size=min(n, len(st)), replace=False))
        sub = st.iloc[idx].reset_index(drop=True)
        write_table(sub, p)
        out[tag] = {"n": int(len(sub)), "by_continent": sub.continent.value_counts().to_dict()}
    write_json(out, cfg.path("results", "smoke_subset.json"))
    return out


def run(stage_names: list[str], cfg: Config) -> int:
    stages = {s.name: s for s in _stages()}
    log_path = cfg.path("results", "run_log.jsonl")
    env = {"git_commit": git_commit(cfg.repo_root), "config_sha256": cfg.sha256(), "versions": package_versions()}
    write_json(env, cfg.path("results", "environment.json"))
    failed: dict[str, str] = {}
    for name in stage_names:
        st = stages[name]
        if name == "smoke_subset" and cfg.out_root is None:
            continue
        if cfg.out_root is not None and name in ("clean_test", "repro_checks", "site_diagnostics"):
            log.info("%-18s not part of smoke runs (locked test and targets need the full site set)", name)
            continue
        up = [d for d in st.deps if d in failed]
        if up:
            msg = f"skipped: upstream {', '.join(up)} not available"
            with stage_timer(log_path, name, {"smoke": cfg.out_root is not None}) as rec:
                rec["status_override"] = msg
            failed[name] = msg
            log.warning("%-18s %s", name, msg)
            continue
        log.info("%-18s start", name)
        try:
            with stage_timer(log_path, name, {"smoke": cfg.out_root is not None}) as rec:
                try:
                    rec["result"] = st.func(cfg)
                except SourceUnavailableError as e:
                    rec["status_override"] = f"blocked: {e}"
                    failed[name] = f"blocked: {e}"
            log.info("%-18s %s (%.1fs)", name, "BLOCKED" if name in failed else "done", rec["seconds"])
        except Exception as e:  # noqa: BLE001 - record and continue with independent stages
            failed[name] = f"error: {type(e).__name__}: {e}"
            log.exception("%s failed", name)
    if failed:
        log.warning("stages not completed: %s", failed)
        return 2
    return 0


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
    want = names if "all" in a.stage else a.stage
    bad = [s for s in want if s not in names]
    if bad:
        ap.error(f"unknown stage(s): {bad}; choose from {names}")
    cfg = load_config(a.config)
    if a.smoke:
        cfg = load_config(a.config, out_root=cfg.path("interim", "smoke"))
    return run(want, cfg)


if __name__ == "__main__":
    sys.exit(main())
