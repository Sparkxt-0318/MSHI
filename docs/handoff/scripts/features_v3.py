"""Attach v3 features to v3 site tables.
WorldClim 2.1 2.5' (19 bioclim), SoilGrids 2.0 5-15 cm mean at 0.05 deg, MODIS NPP (MOD17A3HGF) and
LST day/night (MOD11A2) 2020-2024 window means from modis_points.py. Nearest-pixel sampling for rasters.
Usage: python features_v3.py DL_DIR V3_DIR
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, rasterio

DL, V3 = Path(sys.argv[1]), Path(sys.argv[2])
SG = {"soc": .1, "nitrogen": .01, "phh2o": .1, "clay": .1, "sand": .1, "silt": .1, "bdod": .01, "cec": .1}


def sample(path, lon, lat):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], dtype="float64")
        if s.nodata is not None: v[v == s.nodata] = np.nan
    return v


npp = pd.read_parquet(V3 / "modis_npp_points.parquet")[["site_key", "npp", "npp_n"]]
lst_path = V3 / "modis_lst_points.parquet"
lst = pd.read_parquet(lst_path)[["site_key", "lst_day", "lst_night"]] if lst_path.exists() else None
for tag in ["qc", "repo"]:
    d = pd.read_parquet(V3 / f"sites_v3_{tag}.parquet")
    lon, lat = d.lon.values, d.lat.values
    for i in range(1, 20):
        v = sample(DL / f"worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif", lon, lat)
        d[f"bio{i:02d}"] = np.where(v < -1e30, np.nan, v)
    for k, sc in SG.items():
        v = sample(DL / f"soilgrids05/{k}_5-15cm_global_0p05.tif", lon, lat)
        d[k] = np.where(v > 0, v * sc, np.nan)
    d["site_key"] = d.lat.round(5).astype(str) + "_" + d.lon.round(5).astype(str)
    d = d.merge(npp, on="site_key", how="left")
    if lst is not None:
        d = d.merge(lst, on="site_key", how="left"); d["lst_diurnal_range"] = d.lst_day - d.lst_night
    d.to_parquet(V3 / f"features_v3_{tag}.parquet", index=False)
    print(tag, d.shape, "missing:", d[["bio01", "clay", "npp"] + (["lst_day"] if lst is not None else [])].isna().sum().to_dict())
