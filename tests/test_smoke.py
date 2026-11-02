"""Smoke test on a 50-site subset: site build -> subset -> features -> locked-test machinery.

Uses the real pinned SRDB/COSORE/Natural Earth inputs when present. Gridded features come from tiny
synthetic rasters and the target is replaced by a synthetic one, so no real Europe outcome is ever
scored here (the Europe test is closed; see docs/handoff/ANALYSIS_PLAN_LOCKED.md).
"""
import copy
import shutil

import numpy as np
import pandas as pd
import pytest

from conftest import raw_available
from mshi.config import Config


def _wgs_raster(path, values, dtype="float32"):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


@pytest.mark.data
def test_smoke_50_sites(cfg, tmp_path, monkeypatch):
    if not raw_available(cfg) or not cfg.path("derived", "cosore_annual.csv").exists():
        pytest.skip("pinned raw inputs / cosore_annual.csv not present; run `make data` first")
    from mshi.analysis.clean_test import LockedTest
    from mshi.data import features as F
    from mshi.data.modis import modis_cache_key, modis_point_set, site_key, write_modis_cache
    from mshi.io import StaleInputError, require_outputs, write_result
    from mshi.run import run

    data = copy.deepcopy(cfg.data)
    sand = Config(data, source=cfg.source, out_root=tmp_path)
    sand.path("derived").mkdir(parents=True)
    # stands in for cosore_annual: the committed table, recorded as the output of a current result
    csv = sand.path("derived", "cosore_annual.csv")
    shutil.copy(cfg.path("derived", "cosore_annual.csv"), csv)
    write_result(sand, {"seeded_from": "data/derived/cosore_annual.csv"}, "cosore_annual.json", outputs=[csv])
    assert run(["build_sites", "smoke_subset"], sand) == 0
    for tag in ("qc", "repo"):
        st = pd.read_parquet(sand.path("derived", f"sites_v3_{tag}.parquet"))
        assert len(st) == cfg["smoke"]["n_sites"]
    # smoke_subset re-recorded the subset tables as build_sites' outputs, so later stages accept them
    require_outputs(sand, "build_sites.json", [sand.path("derived", f"sites_v3_{t}.parquet") for t in ("qc", "repo")])

    # synthetic global rasters (1 deg): smooth fields so every site gets a finite value
    rng = np.random.default_rng(0)
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    paths = {}
    rdir = sand.path("interim", "synthetic_rasters")              # under a paths root, so it can be recorded
    rdir.mkdir(parents=True)
    for i in range(1, 20):
        v = 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2
        _wgs_raster(rdir / f"wc{i}.tif", v + rng.normal(0, 0.1, v.shape))
        paths[("wc", i)] = rdir / f"wc{i}.tif"
    for k in cfg["sources"]["soilgrids"]["variables"]:
        _wgs_raster(rdir / f"{k}.tif", 100 + 50 * np.cos(np.radians(lon)) ** 2, dtype="int16")
        paths[("sg", k)] = rdir / f"{k}.tif"
    monkeypatch.setattr(F, "worldclim_path", lambda c, i: paths[("wc", i)])
    monkeypatch.setattr(F, "soilgrids_path", lambda c, v: paths[("sg", v)])
    # stand in for the fetch stages: the synthetic rasters, recorded as their outputs
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json", outputs=[paths[("wc", i)] for i in range(1, 20)])
    write_result(sand, {"synthetic": True}, "fetch_soilgrids.json",
                 outputs=[paths[("sg", k)] for k in cfg["sources"]["soilgrids"]["variables"]])
    pts = modis_point_set(sand)
    assert len(pts) <= 2 * cfg["smoke"]["n_sites"]           # smoke runs exclude the 889 legacy points
    mod = pd.DataFrame({"site_key": site_key(pts.lat, pts.lon).values,
                        "npp": 300 + 3 * pts.lat.abs().values, "npp_n": 5,
                        "lst_day": 20 - 0.3 * pts.lat.abs().values, "lst_night": 5 - 0.3 * pts.lat.abs().values})
    out = write_modis_cache(sand, mod, modis_cache_key(sand, mod.site_key), {"n_failed_reads": 0})
    write_result(sand, {"n_failed_reads": 0, "synthetic": True}, "modis_points.json", outputs=[out])
    res = F.features(sand)
    assert {"qc", "repo"} <= set(res)
    d = pd.read_parquet(sand.path("interim", "features_v3_qc.parquet"))
    assert d[["bio01", "bio12", "clay", "npp", "lst_diurnal_range"]].notna().all().all()
    _wgs_raster(paths[("wc", 1)], np.zeros((180, 360)))       # a raster replaced after it was recorded
    with pytest.raises(StaleInputError, match="wc1.tif changed after the run"):
        F.features(sand)

    # locked-test machinery on synthetic targets (fast settings; the real definition is hash-locked)
    d["log_rs"] = 5.5 + 0.03 * d.bio01 + 0.2 * np.log(d.bio12) + rng.normal(0, 0.3, len(d))
    d["continent"] = np.where(np.arange(len(d)) % 3 == 0, "Europe", "Asia")
    data["clean_test"]["locked"]["rf"]["n_estimators"] = 30
    data["clean_test"]["locked"]["xgb"]["n_estimators"] = 30
    data["clean_test"]["locked"]["bootstrap_n"] = 50
    data["clean_test"]["locked"]["seed_spread"] = [0, 1]
    R = LockedTest(Config(data, source=cfg.source, out_root=tmp_path), require_lock=False).run(d)
    assert len(R["selection_table"]) == 11
    assert {"primary", "aoa", "all_candidates_on_test"} <= set(R)
    assert R["primary"]["n"] > 0 and len(R["all_candidates_on_test"]) == 11
