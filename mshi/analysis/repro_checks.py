"""Compare pipeline outputs with the handoff's reproduction targets (PROMPT section 4).

Writes results/reproduction_check.json and results/reproduction_check.md. Every row is PASS, FAIL,
or NOT RUN (with the reason, e.g. an upstream source blocked by the network policy). Nothing is
estimated or filled in for rows that could not be computed.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from ..config import Config
from ..io import read_table, write_json
from ..data.modis import site_key

log = logging.getLogger("mshi.repro")


def _tol_ok(value: float, target: dict) -> tuple[bool, str]:
    t = target["value"]
    if "abs" in target:
        ok = abs(value - t) <= target["abs"] + 1e-12
        tol = "exact" if target["abs"] == 0 else f"±{target['abs']}"
    else:
        ok = abs(value - t) <= target["rel"] * abs(t) + 1e-12
        tol = f"±{target['rel'] * 100:g}%"
    return ok, tol


def _row(name: str, target: dict, value, note: str = "") -> dict:
    if value is None:
        tol = "exact" if target.get("abs", None) == 0 else (f"±{target['abs']}" if "abs" in target else f"±{target['rel'] * 100:g}%")
        return {"quantity": name, "handoff": target["value"], "v3": None, "tolerance": tol, "status": "NOT RUN", "note": note}
    ok, tol = _tol_ok(float(value), target)
    diff = float(value) - target["value"]
    return {"quantity": name, "handoff": target["value"], "v3": value, "diff": round(diff, 6),
            "rel_diff": round(diff / target["value"], 6) if target["value"] else None,
            "tolerance": tol, "status": "PASS" if ok else "FAIL", "note": note}


def _load(path):
    return json.loads(path.read_text()) if path.exists() else None


def npp_correlation(cfg: Config) -> dict | None:
    mp = cfg.path("interim", "modis_points.parquet")
    if not mp.exists():
        return None
    v3 = pd.read_parquet(mp)[["site_key", "npp", "npp_n"]]
    frames = [read_table(cfg, cfg.repo_path(rel)) for rel in cfg["legacy_allowlist"]]
    o = pd.concat(frames, ignore_index=True)
    o["site_key"] = site_key(o.latitude, o.longitude, cfg["features"]["site_key_round"]).values
    m = o.merge(v3, on="site_key", how="left", suffixes=("_committed", "_v3"))
    both = m.npp_committed.notna() & m.npp_v3.notna()
    r = float(np.corrcoef(m.npp_committed[both], m.npp_v3[both])[0, 1]) if both.sum() > 2 else None
    return {"n_original_sites": int(len(o)), "n_both_valid": int(both.sum()), "pearson_r": r,
            "committed_missing_v3_present": int((m.npp_committed.isna() & m.npp_v3.notna()).sum()),
            "committed_present_v3_missing": int((m.npp_committed.notna() & m.npp_v3.isna()).sum()),
            "ratio_v3_over_committed_median": float(np.median(m.npp_v3[both] / m.npp_committed[both])) if both.any() else None}


def repro_checks(cfg: Config) -> dict:
    T = cfg["reproduction_targets"]
    res_dir = cfg.path("results")
    rows = []
    run_log = res_dir / "run_log.jsonl"
    blocked = {}
    if run_log.exists():
        for line in run_log.read_text().splitlines():
            rec = json.loads(line)
            if str(rec.get("status", "")).startswith("blocked"):
                blocked[rec["stage"]] = rec["status"]
            elif rec.get("status") == "ok":
                blocked.pop(rec["stage"], None)

    def why(*stages):
        import re
        hosts = []
        for s in stages:
            if s in blocked:
                m = re.search(r"https?://([^/:]+)", blocked[s])
                hosts.append(f"{s} ({m.group(1) if m else 'unreachable'})")
        if hosts:
            return "source blocked by network policy: " + ", ".join(hosts)
        return "stage output missing (not run)"

    cs = _load(res_dir / "cosore_annual.json")
    rows.append(_row("COSORE sites with an annual value", T["cosore_sites"], cs and cs["n_sites"],
                     "" if cs else why("fetch_cosore", "cosore_annual")))
    b = _load(res_dir / "build_sites.json")
    nr = "" if b else why("fetch_srdb", "fetch_naturalearth", "build_sites")
    rows.append(_row("SRDB records after repo filters", T["srdb_repo_filter_records"], b and b["srdb_repo_filter_records"], nr))
    rows.append(_row("Records after coordinate check", T["records_after_coord_check"], b and b["records_after_coord_check"], nr))
    rows.append(_row("Records after QC", T["records_after_qc"], b and b["records_after_qc"], nr))
    for k, t in T["qc_removed_by"].items():
        rows.append(_row(f"QC removals: {k}", t, b and b["qc_removed_by"][k], nr))
    for k, t in T["sites_qc_by_continent"].items():
        rows.append(_row(f"QC sites: {k}", t, b and b["sites_qc"]["by_continent"].get(k, 0), nr))
    rows.append(_row("QC sites: total", T["sites_qc_total"], b and b["sites_qc"]["n"], nr))
    rows.append(_row("Repo-filter sites: total", T["sites_repo_total"], b and b["sites_repo"]["n"], nr))

    lt = T["locked_test"]
    ct = _load(res_dir / "clean_test_rerun_qc.json")
    nr = "" if ct else why("fetch_worldclim", "fetch_soilgrids", "modis_points", "features", "clean_test")
    sel = None if not ct else f"{ct['selected']['learner']} ({ct['selected']['set']})"
    rows.append({"quantity": "Locked test: selected model", "handoff": lt["selected"], "v3": sel, "tolerance": "same model",
                 "status": "NOT RUN" if not ct else ("PASS" if ct["selected"]["learner"] == lt["selected"] else "FAIL"),
                 "note": nr})
    rows.append(_row("Locked test: Asia spatial-CV R²", lt["asia_cv_r2"], ct and ct["selected"]["cv_r2"], nr))
    rows.append(_row("Locked test: Europe n", lt["europe_n"], ct and ct["primary"]["n"], nr))
    rows.append(_row("Locked test: Europe R²", lt["europe_r2"], ct and ct["primary"]["r2"], nr))
    rows.append(_row("Locked test: site-bootstrap CI low", lt["europe_ci_lo"], ct and ct["primary"]["ci_site"][0], nr))
    rows.append(_row("Locked test: site-bootstrap CI high", lt["europe_ci_hi"], ct and ct["primary"]["ci_site"][1], nr))

    npp = npp_correlation(cfg)
    rows.append(_row("NPP r vs committed NPP (original 889 sites)", T["npp_corr_original_sites"],
                     npp and npp["pearson_r"], "" if npp else why("modis_points")))
    out = {"rows": rows, "npp_check": npp,
           "summary": {s: sum(r["status"] == s for r in rows) for s in ["PASS", "FAIL", "NOT RUN"]}}
    write_json(out, res_dir / "reproduction_check.json")
    (res_dir / "reproduction_check.md").write_text(to_markdown(rows))
    return out["summary"]


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
    return "\n".join(lines) + "\n"
