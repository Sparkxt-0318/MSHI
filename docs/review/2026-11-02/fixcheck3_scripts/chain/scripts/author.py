"""Build, in a non-smoke sandbox, the state the author's networked `make all` would leave (Phase 1 complete):
committed build results, synthetic rasters recorded by fetch_worldclim/fetch_soilgrids, a synthetic MODIS
extraction recorded by modis_points (NPP built from the committed legacy NPP, so r ~ 0.98), the real
`features` stage on those inputs, and clean_test re-run results = the locked results (no scoring)."""
import json
import numpy as np
import pandas as pd
import cc
from mshi.io import write_result, read_table


def wgs_raster(path, values, dtype="float32"):
    import rasterio
    from rasterio.transform import from_origin
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


def fake_fetch_rasters(sand, seed=0):
    from mshi.data.rasters import soilgrids_path, worldclim_path
    rng = np.random.default_rng(seed)
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    wc = []
    for i in range(1, 20):
        v = 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2
        p = worldclim_path(sand, i)
        wgs_raster(p, v + rng.normal(0, 0.1, v.shape))
        wc.append(p)
    sg = []
    for k in sand["sources"]["soilgrids"]["variables"]:
        p = soilgrids_path(sand, k)
        wgs_raster(p, 100 + 50 * np.cos(np.radians(lon)) ** 2, dtype="int16")
        sg.append(p)
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json", outputs=wc)
    write_result(sand, {"synthetic": True}, "fetch_soilgrids.json", outputs=sg)


def fake_modis_values(sand, noise=0.1923, seed=1):
    """A MODIS table over the stage's point set; NPP at the original sites = committed NPP + noise."""
    from mshi.data.modis import modis_point_set, site_key
    nd = sand["features"]["site_key_round"]
    pts = modis_point_set(sand)
    o = pd.concat([read_table(sand, sand.repo_path(rel)) for rel in sand["legacy_allowlist"]], ignore_index=True)
    o["site_key"] = site_key(o.latitude, o.longitude, nd).values
    o = o.drop_duplicates("site_key")
    rng = np.random.default_rng(seed)
    base = o.set_index("site_key")["npp"]
    sd = float(base.std())
    npp = pd.Series(rng.normal(600, 200, len(pts)), index=pts.site_key.values)
    common = base.index.intersection(npp.index)
    have = base.loc[common].notna()
    npp.loc[common[have.values]] = base.loc[common[have.values]].values + rng.normal(0, noise * sd, int(have.sum()))
    return pd.DataFrame({"site_key": pts.site_key.values, "npp": npp.values, "npp_n": 5,
                         "lst_day": 20 - 0.3 * pts.lat.abs().values, "lst_night": 5 - 0.3 * pts.lat.abs().values})


def fake_modis_stage(sand, table):
    """What modis_points writes after a complete extraction (cache + sidecar + result recording the parquet)."""
    from mshi.data.modis import modis_cache_key, write_modis_cache
    key = modis_cache_key(sand, table.site_key)
    rec = {"n_points": int(len(table)), "n_failed_reads": 0, "cache_key": key, "synthetic": True}
    out = write_modis_cache(sand, table, key, rec)
    write_result(sand, rec, "modis_points.json", outputs=[out])


def locked_reruns(sand):
    locked = {t: json.loads(sand.repo_path(f["file"]).read_text()) for t, f in sand["clean_test"]["locked_results"].items()}
    vs = {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}
    for t in ("qc", "repo"):
        write_result(sand, {**locked[t], "vs_locked": vs, "lock": {"locked_sha256": sand["clean_test"]["locked_sha256"]}},
                     f"clean_test_rerun_{t}.json")


def build(name, base=None):
    from mshi.run import run
    sand = cc.full_sand(name, base=base)
    cc.seed_committed(sand)
    fake_fetch_rasters(sand)
    fake_modis_stage(sand, fake_modis_values(sand))
    code_f = run(["features"], sand)
    locked_reruns(sand)
    code_r = run(["repro_checks"], sand)
    return sand, code_f, code_r
