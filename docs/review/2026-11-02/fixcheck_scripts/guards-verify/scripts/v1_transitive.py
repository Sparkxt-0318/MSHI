"""Claim 1: provenance is per stage, not transitive.

Sandboxes start from a copy of the COMMITTED state (results/*.json, run_log.jsonl and data/derived tables),
so unlike the reviewer's t15 sandbox the stale upstream result JSON (cosore_annual.json) is present.

  python v1_transitive.py direct   config B (cosore rs_range [50,1000]); build_sites alone, then compare with
                                   the full chain under B
  python v1_transitive.py reverse  config C (molar_mass_c 12.011 -> 12.0: values change, counts may not);
                                   build_sites first, cosore_annual second (two invocations)
  python v1_transitive.py features config C; features alone on the committed (config-A) site tables, then
                                   make-data stages; clean_test's features.json check evaluated
"""
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path, sandbox  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import mshi.netutil as N  # noqa: E402

# git verification of the COSORE checkout is not what claim 1 is about; stub it so no git command touches
# the real checkout under data/raw (read-only rule)
N.verify_git_checkout = lambda dest, commit: {"commit": commit, "tree": "-"}
from mshi.io import read_json, result_staleness  # noqa: E402
from mshi.run import run  # noqa: E402

RAW = Path(REPO) / "data" / "raw"


def seed(cfg, committed_state=True):
    """raw inputs (copies; COSORE checkout symlinked read-only) + optionally the committed outputs."""
    d = cfg.path("raw", "srdb", "02163a72"); d.mkdir(parents=True, exist_ok=True)
    for f in ("srdb-data.csv", "LICENSE"):
        shutil.copy(RAW / "srdb" / "02163a72" / f, d / f)
    d = cfg.path("raw", "naturalearth", "v5.1.2"); d.mkdir(parents=True, exist_ok=True)
    shutil.copy(RAW / "naturalearth" / "v5.1.2" / "ne_50m_admin_0_countries.geojson", d)
    cfg.path("raw", "cosore").mkdir(parents=True, exist_ok=True)
    os.symlink(RAW / "cosore" / "02f32e8e", cfg.path("raw", "cosore", "02f32e8e"))
    if committed_state:
        shutil.copytree(Path(REPO) / "results", cfg.path("results"))
        shutil.copytree(Path(REPO) / "data" / "derived", cfg.path("derived"))
    else:
        cfg.path("results").mkdir(parents=True)
        cfg.path("derived").mkdir(parents=True)


def staleness_all(cfg):
    out = {}
    for p in sorted(cfg.path("results").glob("*.json")):
        out[p.name] = result_staleness(cfg, read_json(p))
    return out


def repro(cfg):
    rc = read_json(cfg.path("results", "reproduction_check.json"))
    rows = [(r["quantity"][:38], r["v3"], r["status"], (r.get("note") or "")[:60]) for r in rc["rows"][:17]]
    return rc["summary"], rows


def regression_emulation(cfg):
    """What tests/conftest.py::load_result + tests/test_regression.py would conclude on this results dir."""
    T = cfg["reproduction_targets"]
    verdict = {}
    for name in ("cosore_annual.json", "build_sites.json", "reproduction_check.json"):
        obj = read_json(cfg.path("results", name))
        st = result_staleness(cfg, obj)
        verdict[name] = "FAIL (stale: %s)" % st if st else "loaded"
    b = read_json(cfg.path("results", "build_sites.json"))
    ok = all(abs(b[k] - T[t]["value"]) <= T[t].get("abs", 0) + 1e-12
             for k, t in [("records_after_qc", "records_after_qc"),
                          ("srdb_repo_filter_records", "srdb_repo_filter_records")])
    verdict["test_record_and_site_counts(core rows)"] = ("pass" if ok and verdict["build_sites.json"] == "loaded"
                                                         else "fail")
    rc = read_json(cfg.path("results", "reproduction_check.json"))
    verdict["test_reproduction_table_has_no_fail"] = (
        "fail" if verdict["reproduction_check.json"] != "loaded" or rc["summary"]["FAIL"] or rc["summary"]["STALE"]
        else "pass")
    c = read_json(cfg.path("results", "cosore_annual.json"))
    verdict["test_cosore_sites"] = ("fail" if verdict["cosore_annual.json"] != "loaded"
                                    or c["n_sites"] != T["cosore_sites"]["value"] else "pass")
    return verdict


def direct():
    W = WORK / "v1_direct"; shutil.rmtree(W, ignore_errors=True)
    B = lambda d: d["cosore_annual"].__setitem__("rs_range", [50.0, 1000.0])  # noqa: E731
    full = sandbox(W / "fullB", edit=B); seed(full, committed_state=False)
    print("[direct] full chain under B: run([cosore_annual, build_sites]) exit", run(["cosore_annual", "build_sites"], full))
    fb = read_json(full.path("results", "build_sites.json"))
    part = sandbox(W / "partB", edit=B); seed(part, committed_state=True)
    print("[direct] committed state, config B: staleness before any run:",
          sorted(set(v for v in staleness_all(part).values())))
    code = run(["build_sites", "repro_checks"], part)
    print("[direct] run([build_sites, repro_checks]) under B on committed (config-A) cosore_annual.csv: exit", code)
    pb = read_json(part.path("results", "build_sites.json"))
    for k in ("cosore_records", "records_after_qc", "records_after_coord_check"):
        print(f"   {k:26s} full chain B {fb[k]:5d} | partial B {pb[k]:5d}")
    print("   sites_qc by continent full B:", fb["sites_qc"]["by_continent"])
    print("   sites_qc by continent part B:", pb["sites_qc"]["by_continent"])
    print("   staleness after partial run:", staleness_all(part))
    s, rows = repro(part)
    print("   repro summary:", s)
    for r in rows[:5]:
        print("     ", r)
    print("   regression-test emulation:", regression_emulation(part))


def reverse():
    W = WORK / "v1_reverse"; shutil.rmtree(W, ignore_errors=True)
    C = lambda d: d["cosore_annual"].__setitem__("molar_mass_c", 12.0)  # noqa: E731
    full = sandbox(W / "fullC", edit=C); seed(full, committed_state=False)
    print("[reverse] full chain under C: exit", run(["cosore_annual", "build_sites"], full))
    s2 = sandbox(W / "revC", edit=C); seed(s2, committed_state=True)
    print("[reverse] step 1 run([build_sites, repro_checks]) exit", run(["build_sites", "repro_checks"], s2))
    s, _ = repro(s2); print("   repro summary after step 1:", s)
    print("   regression emulation after step 1:", regression_emulation(s2))
    print("[reverse] step 2 run([cosore_annual, repro_checks]) exit", run(["cosore_annual", "repro_checks"], s2))
    s, rows = repro(s2); print("   repro summary after step 2:", s)
    print("   staleness after step 2:", staleness_all(s2))
    print("   regression emulation after step 2:", regression_emulation(s2))
    fb, rb = read_json(full.path("results", "build_sites.json")), read_json(s2.path("results", "build_sites.json"))
    fb.pop("_provenance"); rb.pop("_provenance")
    print("   build_sites.json (sans provenance) equal full-C vs reverse-C:", fb == rb)
    for tag in ("qc", "repo"):
        a = pd.read_parquet(full.path("derived", f"sites_v3_{tag}.parquet"))
        b = pd.read_parquet(s2.path("derived", f"sites_v3_{tag}.parquet"))
        cos = a.n_cosore > 0
        d = np.abs(a.log_rs.values - b.log_rs.values)
        print(f"   sites_v3_{tag}: n {len(a)} vs {len(b)}; sites with COSORE records {int(cos.sum())}; "
              f"max |log_rs full-C - reverse-C| {d.max():.3e}; sites differing {int((d > 0).sum())}")
    ca = pd.read_csv(full.path("derived", "cosore_annual.csv"))
    cb = pd.read_csv(s2.path("derived", "cosore_annual.csv"))
    print("   cosore_annual.csv equal (full-C vs reverse-C, after step 2):", ca.equals(cb))


def _synthetic_rasters(cfg):
    import rasterio
    from rasterio.transform import from_origin
    from mshi.data.rasters import soilgrids_path, worldclim_path
    rng = np.random.default_rng(0)
    paths = [worldclim_path(cfg, i) for i in range(1, cfg["features"]["worldclim_vars"] + 1)]
    paths += [soilgrids_path(cfg, v) for v in cfg["sources"]["soilgrids"]["variables"]]
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        a = rng.uniform(1, 100, (180, 360)).astype("float32")
        with rasterio.open(p, "w", driver="GTiff", width=360, height=180, count=1, dtype="float32",
                           crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
            dst.write(a, 1)


def _modis_cache(cfg):
    from mshi.data.modis import modis_cache_key, site_key
    from mshi.io import write_json, write_table
    nd = cfg["features"]["site_key_round"]
    keys = set()
    for tag in cfg["site_build"]["variants"]:
        st = pd.read_parquet(cfg.path("derived", f"sites_v3_{tag}.parquet"))
        keys |= set(site_key(st.lat, st.lon, nd))
    keys = sorted(keys)
    df = pd.DataFrame({"site_key": keys, "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                       "lst_night": 5.0, "lst_night_n": 60})
    write_table(df, cfg.path("interim", "modis_points.parquet"))
    write_json({"key": modis_cache_key(cfg, keys), "record": {"n_failed_reads": 0}},
               cfg.path("interim", "modis_points.meta.json"))


def features_path():
    W = WORK / "v1_features"; shutil.rmtree(W, ignore_errors=True)
    C = lambda d: d["cosore_annual"].__setitem__("molar_mass_c", 12.0)  # noqa: E731
    s3 = sandbox(W / "featC", edit=C); seed(s3, committed_state=True)
    _synthetic_rasters(s3); _modis_cache(s3)
    print("[features] step 1 (make features without make data) run([features]) exit", run(["features"], s3))
    fj = read_json(s3.path("results", "features.json"))
    print("   features.json staleness:", result_staleness(s3, fj), "| build_sites.json staleness:",
          result_staleness(s3, read_json(s3.path("results", "build_sites.json"))))
    print("[features] step 2 (make data stages) run([cosore_annual, build_sites, repro_checks]) exit",
          run(["cosore_annual", "build_sites", "repro_checks"], s3))
    s, _ = repro(s3); print("   repro summary:", s)
    st = staleness_all(s3)
    print("   staleness of every result JSON:", st)
    # clean_test.py:258-261, the only input check besides the lock
    p = s3.path("results", "features.json")
    stale = result_staleness(s3, read_json(p) if p.exists() else None)
    print("   clean_test features.json check (clean_test.py:258-261) ->", "REFUSE: " + stale if stale else "passes")
    f = pd.read_parquet(s3.path("interim", "features_v3_qc.parquet"))
    sites = pd.read_parquet(s3.path("derived", "sites_v3_qc.parquet"))
    d = np.abs(f.log_rs.values - sites.log_rs.values)
    print(f"   features_v3_qc.log_rs vs current sites_v3_qc.log_rs: max |diff| {d.max():.3e}, rows differing "
          f"{int((d > 0).sum())} of {len(d)}")


if __name__ == "__main__":
    {"direct": direct, "reverse": reverse, "features": features_path}[sys.argv[1]]()
