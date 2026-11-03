"""Check 5b: the aoa_sensitivity stage end to end on its real code path, with synthetic stand-ins only for the WorldClim
values: 19 synthetic bioclim GeoTIFFs at 10' on the Natural Earth 1:50m land mask (recorded as outputs of a sandbox
fetch_worldclim result), the real Natural Earth subunits (copied into the sandbox raw dir, pinned hash), the real
analysis QC site coordinates and geographic continents with synthetic climate (sampled from the synthetic rasters)
and a synthetic log Rs (no real outcome is used). Real settings except bootstrap n (200) and the outputs (scratch).
Usage: c5b_aoa_realpath.py <sandbox_name> [grid_deg]"""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import copy
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common import REPO, SCRATCH


def climate_fields(lon, lat):
    alat = np.abs(lat)
    bio01 = 28.0 - 0.55 * alat + 3.0 * np.sin(np.radians(lon))
    bio12 = np.clip(300.0 + 1800.0 * np.exp(-(lat / 20.0) ** 2) + 400.0 * np.sin(np.radians(2 * lon)), 10, None)
    f = {1: bio01, 2: 10 + 0.05 * alat, 3: 50 - 0.3 * alat, 4: 200.0 + 25.0 * alat, 5: bio01 + 10.0,
         6: bio01 - 15.0 - 0.25 * alat, 7: 25 + 0.25 * alat, 8: bio01 + 5, 9: bio01 - 5, 10: bio01 + 8, 11: bio01 - 9,
         12: bio12, 13: 0.2 * bio12, 14: 0.02 * bio12, 15: 40.0 + 0.4 * alat + 10 * np.cos(np.radians(lon)),
         16: 0.5 * bio12, 17: 0.08 * bio12, 18: 0.3 * bio12, 19: 0.1 * bio12}
    return {i: np.asarray(v, "float32") for i, v in f.items()}


def main():
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from mshi.config import Config, load_config
    from mshi.io import write_result, write_table
    from mshi.data.rasters import worldclim_path
    from mshi.data.fetch import naturalearth_path
    from mshi.data.features import sample_raster
    from mshi.analysis import aoa as AOA

    name = sys.argv[1]
    grid_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    cfg = load_config()
    data = copy.deepcopy(cfg.data)
    root = Path(SCRATCH) / name
    if root.exists():
        shutil.rmtree(root)
    data["paths"]["raw"] = str(root / "raw")
    data["phase2"]["bootstrap"]["n"] = 200
    data["phase2"]["aoa"]["grid_deg"] = grid_deg
    sand = Config(data, source=cfg.source, out_root=root / "out")
    # Natural Earth (pinned files, copied byte for byte)
    for f in ["ne_50m_admin_0_map_subunits.geojson", "ne_50m_land.geojson"]:
        dst = naturalearth_path(sand, f)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(naturalearth_path(cfg, f), dst)
    # synthetic WorldClim: 10' rasters, NE 1:50m land mask
    res = 1 / 6
    W, H = 2160, 1080
    tr = from_origin(-180.0, 90.0, res, res)
    land = gpd.read_file(naturalearth_path(sand, "ne_50m_land.geojson"))
    mask = rasterize(((g, 1) for g in land.geometry), out_shape=(H, W), transform=tr, fill=0, dtype="uint8")
    lon = -180 + res * (np.arange(W) + 0.5)
    lat = 90 - res * (np.arange(H) + 0.5)
    LON, LAT = np.meshgrid(lon, lat)
    fields = climate_fields(LON, LAT)
    nod = np.float32(-3.4e38)
    tifs = []
    for i in range(1, 20):
        p = worldclim_path(sand, i)
        p.parent.mkdir(parents=True, exist_ok=True)
        a = np.where(mask == 1, fields[i], nod).astype("float32")
        with rasterio.open(p, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs="EPSG:4326",
                           transform=tr, nodata=float(nod), compress="deflate") as dst:
            dst.write(a, 1)
        tifs.append(p)
    write_result(sand, {"synthetic": "10-arcmin stand-in on the NE 1:50m land mask"}, "fetch_worldclim.json",
                 outputs=tifs)
    # sites: real coordinates and geographic continents, synthetic climate and log Rs
    st = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
    st = st[["site_id", "lat", "lon", "continent_geo", "n_rec"]].copy()
    for i in range(1, 20):
        v = sample_raster(worldclim_path(sand, i), st.lon.values, st.lat.values)
        st[f"bio{i:02d}"] = np.where(v < -1e30, np.nan, v)
    rng = np.random.default_rng(5)
    st["log_rs"] = 5.0 + 0.04 * st.bio01 + 0.3 * np.log(st.bio12) + rng.normal(0, 0.4, len(st))
    st["continent"] = "not-a-continent"
    paths = [write_table(st, sand.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
    write_result(sand, {"synthetic": True}, "features_analysis.json", outputs=paths)
    print(f"sites {len(st)}; with complete c8: {int(st[cfg['phase2']['c8']].notna().all(axis=1).sum())}")
    t0 = time.time()
    summ = AOA.aoa_sensitivity(sand)
    print(f"aoa_sensitivity ran in {time.time() - t0:.1f} s")
    print(json.dumps(summ, indent=1))
    r = json.loads(sand.path("results", "aoa_sensitivity.json").read_text())
    print("grid:", json.dumps(r["grid"]["ice_sheets"]), "unassigned", r["grid"]["n_cells_unassigned_continent"])
    print("domains all_land n_cells", r["grid"]["domains"]["all_land"]["n_cells"], "excl",
          r["grid"]["domains"]["excluding_ice_sheets"]["n_cells"])
    print("by continent (all_land):", {k: v["n_cells"] for k, v in r["grid"]["domains"]["all_land"]["by_continent_geo"].items()})
    print("training sets:", {k: (v["n_sites"], v["weights"]["permutation"]["fallback_equal"]) for k, v in r["training_sets"].items()})
    for v in r["variants"]:
        print(v["train"], v["threshold"], v["weights"], round(v["threshold_value"], 4),
              "area out", round(v["all_land"]["area_frac_outside"], 4), round(v["excluding_ice_sheets"]["area_frac_outside"], 4))
    tc = r["transfer_check"]
    print("transfer check all:", tc["all_sites"]["n"], [(x["threshold"], x["weights"], x["inside"]["n"], x["outside"]["n"]) for x in tc["variants"]])


if __name__ == "__main__":
    main()
