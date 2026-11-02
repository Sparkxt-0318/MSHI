"""Regression checks against the handoff reproduction targets (configs/v3.yaml reproduction_targets).

Rows whose stage could not run (e.g. a source blocked by the network policy) are SKIPPED with the
reason, never passed.
"""
import copy
import json
import shutil

import pandas as pd
import pytest

from conftest import load_result, raw_available
from mshi.config import Config


def _within(value, t):
    if "abs" in t:
        return abs(value - t["value"]) <= t["abs"] + 1e-12
    return abs(value - t["value"]) <= t["rel"] * abs(t["value"]) + 1e-12


def _check(value, t, name):
    assert _within(value, t), f"{name}: v3 {value} vs handoff {t['value']} (tolerance {t})"


@pytest.mark.data
def test_cosore_sites(cfg):
    c = load_result(cfg, "cosore_annual.json")
    _check(c["n_sites"], cfg["reproduction_targets"]["cosore_sites"], "COSORE sites")


@pytest.mark.data
def test_record_and_site_counts(cfg):
    T = cfg["reproduction_targets"]
    b = load_result(cfg, "build_sites.json")
    _check(b["srdb_repo_filter_records"], T["srdb_repo_filter_records"], "SRDB repo-filter records")
    _check(b["records_after_coord_check"], T["records_after_coord_check"], "records after coordinate check")
    _check(b["records_after_qc"], T["records_after_qc"], "records after QC")
    for k, t in T["qc_removed_by"].items():
        _check(b["qc_removed_by"][k], t, f"QC removals {k}")
    for k, t in T["sites_qc_by_continent"].items():
        _check(b["sites_qc"]["by_continent"].get(k, 0), t, f"QC sites {k}")
    _check(b["sites_qc"]["n"], T["sites_qc_total"], "QC sites total")
    _check(b["sites_repo"]["n"], T["sites_repo_total"], "repo sites total")


@pytest.mark.data
def test_build_summary_identical_to_handoff(cfg):
    """Stronger than the tolerance table: the v3 build summary equals the handoff's on every shared key."""
    b = load_result(cfg, "build_sites.json")
    h = json.loads(cfg.path("handoff", "build_summary.json").read_text())
    for k, v in h.items():
        assert b[k] == v, k


@pytest.mark.data
def test_locked_test_rerun(cfg):
    T = cfg["reproduction_targets"]["locked_test"]
    ct = load_result(cfg, "clean_test_rerun_qc.json")
    assert ct["selected"]["learner"] == T["selected"]
    _check(ct["selected"]["cv_r2"], T["asia_cv_r2"], "Asia CV R2")
    _check(ct["primary"]["n"], T["europe_n"], "Europe n")
    _check(ct["primary"]["r2"], T["europe_r2"], "Europe R2")
    _check(ct["primary"]["ci_site"][0], T["europe_ci_lo"], "CI low")
    _check(ct["primary"]["ci_site"][1], T["europe_ci_hi"], "CI high")


@pytest.mark.data
@pytest.mark.parametrize("variant", ["qc", "repo"])
def test_locked_rerun_reported_against_locked_result(cfg, variant):
    """Both re-runs (primary and the plan-specified repo-filter sensitivity) carry a deviation block against
    their hash-anchored locked result; the table reports PASS (identical) or DEVIATION, never silence."""
    ct = load_result(cfg, f"clean_test_rerun_{variant}.json")
    assert isinstance(ct["vs_locked"]["identical"], bool) and ct["lock"]["locked_sha256"] == cfg["clean_test"]["locked_sha256"]
    rows = {r["quantity"]: r for r in load_result(cfg, "reproduction_check.json")["rows"]}
    name = ("Locked test: re-run identical to the locked result" if variant == "qc" else
            "Locked test (repo-filter sensitivity): re-run identical to the locked result")
    assert rows[name]["status"] == ("PASS" if ct["vs_locked"]["identical"] else "DEVIATION")


@pytest.mark.data
def test_npp_correlation(cfg):
    rc = load_result(cfg, "reproduction_check.json")
    if not rc.get("npp_check"):
        pytest.skip("NPP check not run (modis_points output missing)")
    t = cfg["reproduction_targets"]["npp_corr_original_sites"]
    _check(rc["npp_check"]["pearson_r"], t, "NPP r")
    assert rc["npp_check"]["n_original_sites"] == t["n_sites"]


@pytest.mark.data
def test_europe_sites_in_the_original_asia_table(cfg):
    """The numbers quoted in docs/DECISIONS.md F-H2 come from the pipeline (site_diagnostics item 5)."""
    d = load_result(cfg, "site_diagnostics.json")
    qc, repo = d["europe_in_original_asia_table_qc"], d["europe_in_original_asia_table_repo"]
    assert (qc["n_europe_sites"], qc["n_within_km"], qc["n_with_identical_record"], qc["n_in_original_box"]) == (236, 30, 28, 30)
    assert qc["by_country_within_km"] == {"Estonia": 13, "Finland": 8, "Latvia": 1, "Romania": 1, "Russia": 7}
    assert (repo["n_europe_sites"], repo["n_within_km"], repo["n_with_identical_record"]) == (284, 38, 38)


@pytest.mark.data
def test_reproduction_table_has_no_fail(cfg):
    rc = load_result(cfg, "reproduction_check.json")
    assert rc["summary"]["FAIL"] == 0, [r for r in rc["rows"] if r["status"] == "FAIL"]
    assert rc["summary"]["STALE"] == 0


@pytest.mark.data
@pytest.mark.slow
def test_fresh_rebuild_matches_committed_tables(cfg, tmp_path):
    """Rebuild COSORE annual + sites from data/raw into a sandbox; must equal the committed derived tables."""
    if not raw_available(cfg):
        pytest.skip("raw SRDB/COSORE/Natural Earth not present; run `make data` first")
    from mshi.data.cosore import cosore_annual
    from mshi.data.sites import build_sites
    sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=tmp_path)
    cosore_annual(sand)
    S = build_sites(sand)
    committed = json.loads(cfg.path("results", "build_sites.json").read_text())
    committed.pop("_provenance", None)
    recorded = committed.pop("_outputs")
    inputs = committed.pop("_inputs")
    assert json.loads(json.dumps(S)) == committed
    fresh = json.loads(sand.path("results", "build_sites.json").read_text())
    assert fresh["_outputs"] == recorded           # byte-identical tables (same SHA-256)
    assert fresh["_inputs"] == inputs              # and a byte-identical cosore_annual.json (same config data)
    for name in ["cosore_annual.csv", "sites_v3_qc.parquet", "sites_v3_repo.parquet", "records_v3.parquet"]:
        a, b = sand.path("derived", name), cfg.path("derived", name)
        rd = pd.read_csv if name.endswith(".csv") else pd.read_parquet
        pd.testing.assert_frame_equal(rd(a), rd(b), check_dtype=False)
    shutil.rmtree(tmp_path, ignore_errors=True)
