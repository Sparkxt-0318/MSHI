"""Compare pipeline outputs with the handoff's reproduction targets (PROMPT section 4).

Writes results/reproduction_check.json and results/reproduction_check.md, then raises
``ReproductionFailure`` (the run exits 1) if any row is FAIL: Phase 1 stops when something does not
reproduce. Row statuses:

- PASS / FAIL: compared with the target and its tolerance (configs/v3.yaml ``reproduction_targets``);
- NOT RUN: no current result. The note gives the reason: the producing stage did not complete in this
  invocation (blocked by the network policy, unreachable, skipped, error), or, if it was not run in
  this invocation, its last status in results/run_log.jsonl. Nothing is estimated or filled in;
- STALE: a result exists but was produced by a different config or code (``_provenance``); re-run;
- DEVIATION: the locked-test re-run differs from the locked result (ground rule 4: report it; the
  locked result stays primary);
- INFO: a handoff number for which the brief gives no tolerance.
"""
from __future__ import annotations

import json
import logging
import re

import numpy as np
import pandas as pd

from ..config import Config
from ..data.modis import StaleModisError, load_modis_points, site_key
from ..io import read_table, result_staleness, write_result

log = logging.getLogger("mshi.repro")

# result file -> stages that produce it or its inputs (upstream first)
PRODUCERS = {
    "cosore_annual.json": ["fetch_cosore", "cosore_annual"],
    "build_sites.json": ["fetch_srdb", "fetch_naturalearth", "fetch_cosore", "cosore_annual", "build_sites"],
    "modis_points.json": ["build_sites", "modis_points"],
    "clean_test_rerun_qc.json": ["build_sites", "fetch_worldclim", "fetch_soilgrids", "modis_points", "features",
                                 "clean_test"],
}
NPP_METHOD = ("method reconstructed [UNVERIFIED]: no handoff script computes this r; Pearson r on raw NPP "
              "at the original sites with a value in both tables, joined on site_key")


class ReproductionFailure(RuntimeError):
    """At least one reproduction target is outside its tolerance."""


def _tol(target: dict) -> str:
    if "abs" in target:
        return "exact" if target["abs"] == 0 else f"±{target['abs']}"
    return f"±{target['rel'] * 100:g}%"


def _tol_ok(value: float, target: dict) -> bool:
    t = target["value"]
    if "abs" in target:
        return abs(value - t) <= target["abs"] + 1e-12
    return abs(value - t) <= target["rel"] * abs(t) + 1e-12


def _row(name: str, target: dict, value, state: str = "OK", note: str = "") -> dict:
    row = {"quantity": name, "handoff": target["value"], "v3": value, "tolerance": _tol(target), "note": note}
    if state == "NOT RUN" or value is None:
        return {**row, "v3": None, "status": "NOT RUN"}
    diff = float(value) - target["value"]
    row.update(diff=round(diff, 6), rel_diff=round(diff / target["value"], 6) if target["value"] else None)
    row["status"] = "STALE" if state == "STALE" else ("PASS" if _tol_ok(float(value), target) else "FAIL")
    return row


def _describe(status: str) -> str:
    kind, _, msg = status.partition(": ")
    host = re.search(r"https?://([^/:\s'\"]+)", msg)
    h = f" ({host.group(1)})" if host else ""
    if kind == "blocked":
        return f"blocked by network policy{h}"
    if kind == "unavailable":
        return f"source unreachable{h}"
    if kind == "error":
        return f"error ({msg.split(':')[0]})"
    return status


def _last_records(res_dir) -> dict:
    p = res_dir / "run_log.jsonl"
    last: dict = {}
    if p.exists():
        for line in p.read_text().splitlines():
            rec = json.loads(line)
            if not rec.get("smoke"):
                last[rec["stage"]] = rec
    return last


def source(cfg: Config, fname: str) -> tuple[dict | None, str, str]:
    """(result, state, note) for a result file; state is OK, STALE or NOT RUN."""
    res_dir = cfg.path("results")
    stages = PRODUCERS[fname]
    status = (cfg.invocation or {}).get("status", {})
    for s in stages:
        st = status.get(s)
        if st is not None and st != "ok":
            return None, "NOT RUN", f"{s}: {_describe(st)}"
    p = res_dir / fname
    obj = json.loads(p.read_text()) if p.exists() else None
    if obj is None or obj.get("status", "").startswith("incomplete"):
        last = _last_records(res_dir)
        for s in stages:
            rec = last.get(s)
            if rec and rec.get("status") != "ok":
                return None, "NOT RUN", f"{s}: {_describe(rec['status'])} (run log, {rec.get('end_utc', '')[:10]})"
        return None, "NOT RUN", "no result (stage not run)"
    stale = result_staleness(cfg, obj)
    if stale:
        return obj, "STALE", f"{fname} {stale}; re-run `make all`"
    return obj, "OK", ""


def npp_correlation(cfg: Config) -> dict:
    v3 = load_modis_points(cfg)[["site_key", "npp", "npp_n"]]
    frames = [read_table(cfg, cfg.repo_path(rel)) for rel in cfg["legacy_allowlist"]]
    o = pd.concat(frames, ignore_index=True)
    o["site_key"] = site_key(o.latitude, o.longitude, cfg["features"]["site_key_round"]).values
    m = o.merge(v3, on="site_key", how="left", suffixes=("_committed", "_v3"))
    both = m.npp_committed.notna() & m.npp_v3.notna()
    r = float(np.corrcoef(m.npp_committed[both], m.npp_v3[both])[0, 1]) if both.sum() > 2 else None
    return {"method": NPP_METHOD, "n_original_sites": int(len(o)), "n_both_valid": int(both.sum()),
            "pearson_r": r,
            "committed_missing_v3_present": int((m.npp_committed.isna() & m.npp_v3.notna()).sum()),
            "committed_present_v3_missing": int((m.npp_committed.notna() & m.npp_v3.isna()).sum()),
            "ratio_v3_over_committed_median": float(np.median(m.npp_v3[both] / m.npp_committed[both])) if both.any() else None}


def repro_checks(cfg: Config) -> dict:
    T = cfg["reproduction_targets"]
    rows = []

    cs, st, note = source(cfg, "cosore_annual.json")
    rows.append(_row("COSORE sites with an annual value", T["cosore_sites"], cs and cs["n_sites"], st, note))

    b, st, note = source(cfg, "build_sites.json")
    g = (lambda f: f(b)) if b else (lambda f: None)
    rows.append(_row("SRDB records after repo filters", T["srdb_repo_filter_records"], g(lambda x: x["srdb_repo_filter_records"]), st, note))
    rows.append(_row("Records after coordinate check", T["records_after_coord_check"], g(lambda x: x["records_after_coord_check"]), st, note))
    rows.append(_row("Records after QC", T["records_after_qc"], g(lambda x: x["records_after_qc"]), st, note))
    for k, t in T["qc_removed_by"].items():
        rows.append(_row(f"QC removals: {k}", t, g(lambda x: x["qc_removed_by"][k]), st, note))
    for k, t in T["sites_qc_by_continent"].items():
        rows.append(_row(f"QC sites: {k}", t, g(lambda x: x["sites_qc"]["by_continent"].get(k, 0)), st, note))
    rows.append(_row("QC sites: total", T["sites_qc_total"], g(lambda x: x["sites_qc"]["n"]), st, note))
    rows.append(_row("Repo-filter sites: total", T["sites_repo_total"], g(lambda x: x["sites_repo"]["n"]), st, note))

    lt = T["locked_test"]
    ct, st, note = source(cfg, "clean_test_rerun_qc.json")
    sel = f"{ct['selected']['learner']} ({ct['selected']['set']})" if ct else None
    rows.append({"quantity": "Locked test: selected model", "handoff": lt["selected"], "v3": sel,
                 "tolerance": "same model", "note": note,
                 "status": "NOT RUN" if not ct else ("STALE" if st == "STALE" else
                                                     ("PASS" if ct["selected"]["learner"] == lt["selected"] else "FAIL"))})
    c = (lambda f: f(ct)) if ct else (lambda f: None)
    rows.append(_row("Locked test: Asia spatial-CV R²", lt["asia_cv_r2"], c(lambda x: x["selected"]["cv_r2"]), st, note))
    rows.append(_row("Locked test: Europe n", lt["europe_n"], c(lambda x: x["primary"]["n"]), st, note))
    rows.append(_row("Locked test: Europe R²", lt["europe_r2"], c(lambda x: x["primary"]["r2"]), st, note))
    rows.append(_row("Locked test: site-bootstrap CI low", lt["europe_ci_lo"], c(lambda x: x["primary"]["ci_site"][0]), st, note))
    rows.append(_row("Locked test: site-bootstrap CI high", lt["europe_ci_hi"], c(lambda x: x["primary"]["ci_site"][1]), st, note))
    vs = ct.get("vs_locked") if ct else None
    rows.append({"quantity": "Locked test: re-run identical to the locked result", "handoff": "identical",
                 "v3": None if not vs else ("identical" if vs["identical"] else f"max |diff| {vs['max_abs_primary_diff']:.3g}"),
                 "tolerance": "1e-9", "note": note if not vs else ("" if vs["identical"] else
                                                                  "deviation: report it; the locked result stays primary"),
                 "status": "NOT RUN" if not vs else ("STALE" if st == "STALE" else
                                                     ("PASS" if vs["identical"] else "DEVIATION"))})

    mp, st, note = source(cfg, "modis_points.json")
    npp = None
    if st == "OK":
        try:
            npp = npp_correlation(cfg)
        except (FileNotFoundError, StaleModisError) as e:
            st, note = "NOT RUN", f"modis_points output unusable: {e}"
    t = T["npp_corr_original_sites"]
    rows.append(_row(f"NPP r vs committed NPP (original {t['n_sites']} sites)", t, npp and npp["pearson_r"], st,
                     note or f"{NPP_METHOD}; n = {npp['n_both_valid']}"))
    t2 = T["npp_recovered_sites"]
    v2 = npp and npp["committed_missing_v3_present"]
    rows.append({"quantity": "Original sites with NPP missing in the committed tables but present in v3",
                 "handoff": t2["value"], "v3": v2, "tolerance": "none given", "status": "INFO" if npp else "NOT RUN",
                 "note": note or "prep_log D8; no tolerance in the brief, reported for information"})

    summary = {s: sum(r["status"] == s for r in rows) for s in ["PASS", "FAIL", "DEVIATION", "STALE", "NOT RUN", "INFO"]}
    out = {"rows": rows, "npp_check": npp, "summary": summary}
    write_result(cfg, out, "reproduction_check.json")
    (cfg.path("results") / "reproduction_check.md").write_text(to_markdown(rows))
    if summary["FAIL"]:
        bad = [r["quantity"] for r in rows if r["status"] == "FAIL"]
        raise ReproductionFailure(f"{summary['FAIL']} reproduction target(s) outside tolerance: {bad}; "
                                  "see results/reproduction_check.md. Stop and report (ground rule 2).")
    return summary


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 10 else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def to_markdown(rows: list[dict]) -> str:
    lines = ["| Quantity | Handoff | v3 | Tolerance | Status | Note |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['quantity']} | {_fmt(r['handoff'])} | {_fmt(r['v3'])} | {r['tolerance']} | "
                     f"{r['status']} | {r.get('note', '')} |")
    lines.append("")
    lines.append("PASS/FAIL: within/outside the tolerance in configs/v3.yaml. NOT RUN: no current result (reason "
                 "in the note). STALE: produced by a different config or code. DEVIATION: the locked-test re-run "
                 "differs from the locked result, which stays primary. INFO: no tolerance given in the brief.")
    return "\n".join(lines) + "\n"
