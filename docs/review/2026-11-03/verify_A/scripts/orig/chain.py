"""Integration run of the whole chain after the gridded sources become reachable, emulated in a full (non-smoke)
sandbox: the real site builds (current code) on the pinned raw inputs (read-only symlinks), then synthetic targets
(no real Rs value is scored anywhere), synthetic land-masked WorldClim/SoilGrids rasters at the paths the pipeline
uses, a synthetic MODIS cache for the real point set, and a fabricated all-PASS reproduction table; then every
Phase-2 stage through mshi.run.run(), with light settings and n_jobs <= 2. Checks: exit code and statuses,
provenance of every result (current, inputs recorded), exploratory labels in results and run log.

usage: chain.py <sandbox-name> [second]   ('second': re-run the Phase-2 stages and compare result bytes)"""
import copy
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import _read_result, require_current, require_outputs, result_staleness, write_result, write_table  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
NAME = sys.argv[1]
SECOND = len(sys.argv) > 2 and sys.argv[2] == "second"
BASE = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb") / NAME
REPO = Path("/home/user/MSHI")


def make_cfg() -> Config:
    cfg0 = load_config()
    d = copy.deepcopy(cfg0.data)
    for root in ("raw", "interim", "derived", "results", "figures"):
        d["paths"][root] = str(BASE / root)
    p2 = d["phase2"]
    p2["noise_ceiling"].update(n_boot=10, n_jobs=1)
    p2["transfer"]["rf"].update(n_estimators=8, grid={"min_samples_leaf": [2, 8], "max_features": [0.5, 1.0]},
                                inner_folds=3, n_jobs=1)
    p2["transfer"]["xgb_light"] = {**d["clean_test"]["locked"]["xgb"], "n_estimators": 12}
    p2["transfer"]["xgb_from"] = "phase2.transfer.xgb_light"
    p2["within"].update(folds=2, seeds=[42, 43])
    p2["within"]["knndm"].update(max_pred_points=300)
    p2["bootstrap"]["n"] = 60
    p2["aoa"].update(perm_repeats=2)
    p2["us_r2"].update(xgb_seed_spread=[0, 1])
    return Config(d, source=cfg0.source)


cfg = make_cfg()
from mshi.run import run  # noqa: E402

STAGES2 = ["noise_ceiling", "europe_geo_sensitivity", "features_analysis", "transfer_matrix", "within_continent",
           "aoa_sensitivity", "us_r2"]


def install_europe_geo_fake():
    """The control of europe_geo_sensitivity compares with the locked result; with synthetic features the locked
    numbers cannot match, so the locked result is replaced (in memory only) by the metrics of the same computation
    on the synthetic features (as tests/test_analysis_build.py does)."""
    from mshi.analysis import clean_test as CT
    from mshi.analysis import europe_geo as EG
    lt = CT.LockedTest(cfg)
    d = pd.read_parquet(cfg.path("interim", "features_v3_qc.parquet"))
    tr, te = d[d.continent == "Asia"], d[d.continent == "Europe"]
    a, e, _f, _m, p = lt.score(tr, te, "TP", "OLS-TP")
    fake = {"selected": {"set": "TP", "learner": "OLS-TP"},
            "primary": lt.metrics(e.log_rs.values, p, e.lon.values, e.lat.values, np.full(len(e), a.log_rs.mean()))}
    real = EG.read_json
    EG.read_json = lambda path: fake if "clean_test_europe" in str(path) else real(path)


if not SECOND:
    raw = BASE / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for sub in ("srdb", "cosore", "naturalearth"):
        if not (raw / sub).exists():
            os.symlink(REPO / "data" / "raw" / sub, raw / sub)
    print("site build exit:", run(["cosore_annual", "cosore_annual_analysis", "build_sites", "build_sites_analysis"], cfg))

    # ---- synthetic targets (records and sites of both builds), results re-recorded with the same inputs
    rng = np.random.default_rng(11)
    for prefix, rec_name, res_name in (("sites_v3", "records_v3.parquet", "build_sites.json"),
                                       ("sites_analysis", "records_analysis.parquet", "build_sites_analysis.json")):
        rp = cfg.path("derived", rec_name)
        r = pd.read_parquet(rp)
        site_eff = {}
        lr = 6.4 - 0.008 * r.lat.abs() + 0.1 * np.sin(np.radians(r.lon)) + rng.normal(0, 0.35, len(r))
        r["rs"] = np.exp(lr)
        r["log_rs"] = lr
        write_table(r, rp)
        outs = [rp]
        for tag in ("qc", "repo"):
            sp = cfg.path("derived", f"{prefix}_{tag}.parquet")
            s = pd.read_parquet(sp)
            g = r.dropna(subset=[f"site_id_{tag}"]).groupby(f"site_id_{tag}").log_rs
            s["log_rs"] = s.site_id.map(g.mean())
            s["log_rs_sd"] = s.site_id.map(g.std())
            s["rs"] = np.exp(s.log_rs)
            assert s.log_rs.notna().all()
            write_table(s, sp)
            outs.append(sp)
        b, _ = _read_result(cfg, res_name)
        ins = dict(b.get("_inputs") or {})
        if "build_sites.json" in ins:
            ins["build_sites.json"] = cfg.reads["build_sites.json"]
        write_result(cfg, {**b, "synthetic_targets": True}, res_name, outputs=outs, inputs=ins)
        require_current(cfg, res_name)

    # ---- synthetic gridded inputs at the pipeline's own paths, recorded as the fetch stages' outputs
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from mshi.data.rasters import soilgrids_path, worldclim_path
    land = gpd.read_file(REPO / "data/raw/naturalearth/v5.1.2/ne_50m_land.geojson")
    tf = from_origin(-180, 90, 0.5, 0.5)
    mask = rasterize(((g, 1) for g in land.geometry), out_shape=(360, 720), transform=tf, all_touched=True,
                     fill=0, dtype="uint8").astype(bool)
    lat = (90 - 0.25 - 0.5 * np.arange(360))[:, None] * np.ones((1, 720))
    lon = np.ones((360, 1)) * (-180 + 0.25 + 0.5 * np.arange(720))[None, :]
    alat = np.abs(lat)
    bio01 = 28 - 0.45 * alat + 0.5 * np.sin(np.radians(lon))
    bio12 = 300 + 1500 * np.exp(-(lat / 25) ** 2) + 3 * np.mod(lon, 60)
    fields = {1: bio01, 4: 200 + 15 * alat, 5: bio01 + 10, 6: bio01 - 10, 12: bio12, 14: bio12 / 30,
              15: 50 + 0.5 * alat + np.cos(np.radians(lon)), 17: bio12 / 8}
    tifs = []
    for i in range(1, 20):
        v = fields.get(i, 10 + i + 0.1 * alat + np.sin(np.radians(2 * lon)))
        v = np.where(mask, v, -3.4e38).astype("float32")
        p = worldclim_path(cfg, i)
        p.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(p, "w", driver="GTiff", width=720, height=360, count=1, dtype="float32", crs="EPSG:4326",
                           transform=tf, nodata=-3.4e38) as dst:
            dst.write(v, 1)
        tifs.append(p)
    write_result(cfg, {"synthetic": True}, "fetch_worldclim.json", outputs=tifs)
    sgs = []
    for k, var in enumerate(cfg["sources"]["soilgrids"]["variables"]):
        v = np.where(mask, 100 + 20 * k + alat, 0).astype("int16")
        p = soilgrids_path(cfg, var)
        p.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(p, "w", driver="GTiff", width=720, height=360, count=1, dtype="int16", crs="EPSG:4326",
                           transform=tf) as dst:
            dst.write(v, 1)
        sgs.append(p)
    write_result(cfg, {"synthetic": True}, "fetch_soilgrids.json", outputs=sgs)

    from mshi.data.modis import modis_cache_key, modis_point_set, write_modis_cache
    require_current(cfg, "build_sites.json")
    require_current(cfg, "build_sites_analysis.json")
    pts = modis_point_set(cfg)
    mod = pd.DataFrame({"site_key": pts.site_key.values, "npp": 300 + 3 * pts.lat.abs().values, "npp_n": 5,
                        "lst_day": 25 - 0.3 * pts.lat.abs().values, "lst_day_n": 60,
                        "lst_night": 10 - 0.3 * pts.lat.abs().values, "lst_night_n": 60})
    out = write_modis_cache(cfg, mod, modis_cache_key(cfg, pts.site_key), {"n_failed_reads": 0, "synthetic": True})
    write_result(cfg, {"n_failed_reads": 0, "synthetic": True}, "modis_points.json", outputs=[out],
                 inputs=["build_sites.json", "build_sites_analysis.json"])
    # ---- fabricated, current, all-PASS reproduction table (the gate is then open for every stage)
    from mshi.analysis.repro_checks import row_group
    qs = ["COSORE sites with an annual value", "QC sites: total", "Locked test: Europe R²",
          "Locked test: re-run identical to the locked result", "NPP r vs committed NPP (original 889 sites)"]
    rows = [{"quantity": q, "status": "PASS", "group": row_group(q)} for q in qs]
    write_result(cfg, {"rows": rows, "summary": {"PASS": len(rows), "FAIL": 0, "DEVIATION": 0, "STALE": 0,
                                                 "NOT RUN": 0, "INFO": 0}, "fabricated_for_review": True},
                 "reproduction_check.json")
    print("features exit:", run(["features"], cfg))

install_europe_geo_fake()
before = {f.name: f.read_bytes() for f in cfg.path("results").glob("*.json")} if SECOND else None
code = run(STAGES2, cfg)
print("Phase-2 stages exit code:", code)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
last = {}
for r in recs:
    last[r["stage"]] = r
for s in STAGES2:
    r = last[s]
    print(f"  {s:24s} status={r['status'][:150]!s:60s} exploratory={r.get('exploratory')} seconds={r['seconds']}")
for s in STAGES2:
    f = {"noise_ceiling": "noise_ceiling.json", "europe_geo_sensitivity": "europe_geo_sensitivity.json",
         "features_analysis": "features_analysis.json", "transfer_matrix": "transfer_matrix.json",
         "within_continent": "within_continent.json", "aoa_sensitivity": "aoa_sensitivity.json",
         "us_r2": "us_r2.json"}[s]
    obj, _ = _read_result(cfg, f)
    if obj is None:
        print(f"  {f}: MISSING")
        continue
    print(f"  {f}: stale={result_staleness(cfg, obj)}; exploratory={obj.get('exploratory')}; inputs="
          f"{sorted(obj.get('_inputs') or {})}; outputs={sorted(obj.get('_outputs') or {})}")
if SECOND:
    after = {f.name: f.read_bytes() for f in cfg.path("results").glob("*.json")}
    for k in sorted(after):
        if k in before and before[k] != after[k]:
            print("  result bytes changed on re-run:", k)
    print("re-run compared:", len(after), "result files")
