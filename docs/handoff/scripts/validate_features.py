"""Check that fresh WorldClim 2.1 10' + SoilGrids 2.0 (0.1 deg WCS) + committed MODIS rasters
reproduce the committed feature tables (nearest-pixel sampling, as in src/features.py)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd, rasterio

REPO, DL = Path(sys.argv[1]), Path(sys.argv[2])
BIO = {"bio01": 1, "bio04": 4, "bio05": 5, "bio06": 6, "bio12": 12, "bio14": 14, "bio15": 15, "bio17": 17}
SG = {"soc": .1, "nitrogen": .01, "phh2o": .1, "clay": .1, "sand": .1, "silt": .1, "bdod": .01, "cec": .1}


def sample(path, lon, lat):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], dtype="float64")
        if s.nodata is not None: v[v == s.nodata] = np.nan
    return v


d = pd.concat([pd.read_parquet(REPO / "data/processed/training_features_v2.parquet"),
               pd.read_parquet(REPO / "data/processed/us_validation_features_v2.parquet")], ignore_index=True)
lon, lat = d.longitude.values, d.latitude.values
out = {}
for k, i in BIO.items():
    v = sample(DL / f"worldclim/wc2.1_10m_bio_{i}.tif", lon, lat)
    m = ~np.isnan(v) & d[k].notna().values
    out[k] = dict(n=int(m.sum()), max_abs_diff=float(np.nanmax(np.abs(v[m] - d[k].values[m]))),
                  frac_exact=float(np.mean(np.isclose(v[m], d[k].values[m], atol=1e-4))))
for k, sc in SG.items():
    v = sample(DL / f"soilgrids/{k}_5-15cm_global_0p1.tif", lon, lat)
    v = np.where(v > 0, v * sc, np.nan)
    m = ~np.isnan(v) & d[k].notna().values
    out[k] = dict(n=int(m.sum()), max_abs_diff=float(np.max(np.abs(v[m] - d[k].values[m]))),
                  frac_exact=float(np.mean(np.isclose(v[m], d[k].values[m], atol=1e-3))),
                  corr=float(np.corrcoef(v[m], d[k].values[m])[0, 1]))
for k in ["npp", "lst_day", "lst_night"]:
    v = sample(REPO / f"data/raw/modis/{k}_2020_2024_mean.tif", lon, lat)
    m = ~np.isnan(v) & d[k].notna().values
    out[k] = dict(n=int(m.sum()), frac_exact=float(np.mean(np.isclose(v[m], d[k].values[m]))),
                  raw_median=float(np.nanmedian(v)), nan_or_le0=int(np.sum(np.isnan(v) | (v <= 0))))
print(json.dumps(out, indent=1))
