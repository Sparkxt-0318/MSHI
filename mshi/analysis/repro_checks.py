"""Compare pipeline outputs with the handoff's reproduction targets (PROMPT section 4).

Writes results/reproduction_check.json and results/reproduction_check.md, then raises
``ReproductionFailure`` (the run exits 1) if any row is FAIL: Phase 1 stops when something does not
reproduce; otherwise ``StaleInputError`` (status ``stale``, exit 2) if any row is STALE. Row statuses:

- PASS / FAIL: compared with the target and its tolerance (configs/v3.yaml ``reproduction_targets``).
  A current result that does not yield the value (e.g. an NPP r that cannot be computed, a re-run
  without its ``vs_locked`` block) is FAIL, with the reason in the note;
- NOT RUN: no result. The note gives the reason: the producing stage did not complete in this
  invocation (blocked by the network policy, unreachable, skipped, error), or, if it was not run in
  this invocation, its last status in results/run_log.jsonl. Nothing is estimated or filled in;
- STALE: a result exists but is not current: produced by a different config or code, or an output file
  it records changed after the run (``mshi.io.result_staleness``); re-run;
- DEVIATION: a locked-test re-run (primary or repo-filter sensitivity) differs from its locked result
  (ground rule 4: report it; the locked result stays primary);
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
from ..io import StaleInputError, read_table, result_staleness, write_result

log = logging.getLogger("mshi.repro")

# result file -> stages that produce it or its inputs (upstream first)
PRODUCERS = {
    "cosore_annual.json": ["fetch_cosore", "cosore_annual"],
    "build_sites.json": ["fetch_srdb", "fetch_naturalearth", "fetch_cosore", "cosore_annual", "build_sites"],
    "modis_points.json": ["build_sites", "modis_points"],
    "clean_test_rerun_qc.json": ["build_sites", "fetch_worldclim", "fetch_soilgrids", "modis_points", "features",
                                 "clean_test"],
    "clean_test_rerun_repo.json": ["build_sites", "fetch_worldclim", "fetch_soilgrids", "modis_points", "features",
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
    if state in ("NOT RUN", "STALE") and value is None:
        return {**row, "v3": None, "status": state}
    if value is None:                 # a current result without this value: it did not reproduce
        return {**row, "v3": None, "status": "FAIL", "note": note or "no value in a current result"}
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
    if kind == "stale":
        return f"stale input ({msg.split(';')[0]})"
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
    atol = cfg["clean_test"]["deviation_atol"]
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
    rows.append(_rerun_row("Locked test: re-run identical to the locked result", ct, st, note, atol))
    ctr, st_r, note_r = source(cfg, "clean_test_rerun_repo.json")
    rows.append(_rerun_row("Locked test (repo-filter sensitivity): re-run identical to the locked result",
                           ctr, st_r, note_r, atol))

    mp, st, note = source(cfg, "modis_points.json")
    npp = None
    if st == "OK":
        try:
            npp = npp_correlation(cfg)
        except (FileNotFoundError, StaleModisError) as e:   # the result is current but its table is not
            st, note = "STALE", f"modis_points output unusable: {e}"
    t = T["npp_corr_original_sites"]
    r_npp = npp["pearson_r"] if npp else None
    if npp and r_npp is None:
        note = f"r not computable: {npp['n_both_valid']} original sites have NPP in both tables"
    rows.append(_row(f"NPP r vs committed NPP (original {t['n_sites']} sites)", t, r_npp, st,
                     note or f"{NPP_METHOD}; n = {npp['n_both_valid']}"))
    t2 = T["npp_recovered_sites"]
    rows.append({"quantity": "Original sites with NPP missing in the committed tables but present in v3",
                 "handoff": t2["value"], "v3": npp["committed_missing_v3_present"] if npp else None,
                 "tolerance": "none given", "status": "INFO" if npp else st,
                 "note": (note if not npp else "prep_log D8; no tolerance in the brief, reported for information")})

    summary = {s: sum(r["status"] == s for r in rows) for s in ["PASS", "FAIL", "DEVIATION", "STALE", "NOT RUN", "INFO"]}
    out = {"rows": rows, "npp_check": npp, "summary": summary}
    md = cfg.path("results", "reproduction_check.md")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(to_markdown(rows))
    write_result(cfg, out, "reproduction_check.json", outputs=[md])
    if summary["FAIL"]:
        bad = [r["quantity"] for r in rows if r["status"] == "FAIL"]
        raise ReproductionFailure(f"{summary['FAIL']} reproduction target(s) outside tolerance: {bad}; "
                                  "see results/reproduction_check.md. Stop and report (ground rule 2).")
    if summary["STALE"]:
        raise StaleInputError(f"{summary['STALE']} reproduction row(s) come from results that are not current; "
                              "see results/reproduction_check.md and re-run `make all`")
    return summary


def _rerun_row(name: str, ct: dict | None, st: str, note: str, atol: float) -> dict:
    """PASS if the re-run is identical to its locked result, DEVIATION if not, FAIL if it has no valid
    ``vs_locked`` block, NOT RUN/STALE as for any other row."""
    row = {"quantity": name, "handoff": "identical", "v3": None, "tolerance": f"{atol:g}", "note": note}
    if ct is None:
        return {**row, "status": st}
    vs = ct.get("vs_locked")
    if not isinstance(vs, dict) or not isinstance(vs.get("identical"), bool):
        return {**row, "status": "STALE" if st == "STALE" else "FAIL",
                "note": note or "re-run result has no valid vs_locked block (compare_with_locked not applied)"}
    d = vs.get("max_abs_primary_diff")
    v3 = "identical" if vs["identical"] else (f"max |diff| {d:.3g}" if isinstance(d, (int, float)) else
                                             "differs (no primary metrics to compare)")
    if not vs.get("selected_same", True):
        v3 += "; another model selected"
    status = "STALE" if st == "STALE" else ("PASS" if vs["identical"] else "DEVIATION")
    return {**row, "v3": v3, "status": status,
            "note": note or ("" if vs["identical"] else "deviation: report it; the locked result stays primary")}


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
    lines.append("PASS/FAIL: within/outside the tolerance in configs/v3.yaml (FAIL also when a current result "
                 "does not yield the value). NOT RUN: no result (reason in the note). STALE: the result is not "
                 "current (another config or code, or an output file changed after the run). DEVIATION: a "
                 "locked-test re-run differs from its locked result, which stays primary. INFO: no tolerance "
                 "given in the brief.")
    return "\n".join(lines) + "\n"
