"""Item 1 Checkpoint 1 — sample the now-real MODIS rasters at training points.

Adds 5 columns to training_features.parquet and us_validation_features.parquet:
    npp, lst_day, lst_night, landcover (refresh), lst_diurnal_range

Saves to:
    data/processed/training_features_v2.parquet         (Asia + MODIS)
    data/processed/us_validation_features_v2.parquet    (US + MODIS)

Does NOT overwrite v1 — they remain available alongside.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"

MODIS = {
    "npp":       RAW / "modis" / "npp_2020_2024_mean.tif",
    "lst_day":   RAW / "modis" / "lst_day_2020_2024_mean.tif",
    "lst_night": RAW / "modis" / "lst_night_2020_2024_mean.tif",
    "landcover": RAW / "modis" / "landcover_igbp_2023.tif",
}


def sample_raster(raster_path, lons, lats):
    with rasterio.open(raster_path) as src:
        coords = list(zip(lons, lats))
        vals = np.array([v[0] for v in src.sample(coords)], dtype="float64")
        nd = src.nodata
        if nd is not None:
            vals = np.where(vals == nd, np.nan, vals)
    return vals


def enrich(df_path: Path, out_path: Path, label: str):
    df = pd.read_parquet(df_path)
    n0 = len(df)
    cols0 = list(df.columns)
    print(f"\n[{label}] {df_path.name}  in: {n0} rows × {len(cols0)} cols")

    lons = df["longitude"].to_numpy()
    lats = df["latitude"].to_numpy()
    for var, path in MODIS.items():
        df[var] = sample_raster(path, lons, lats)
    # Engineered
    df["lst_diurnal_range"] = df["lst_day"] - df["lst_night"]

    df.to_parquet(out_path, index=False)
    print(f"[{label}] wrote {out_path.name}  out: {len(df)} rows × {len(df.columns)} cols")

    new_feats = ["npp", "lst_day", "lst_night", "landcover", "lst_diurnal_range"]
    print(f"[{label}] new feature stats:")
    for f in new_feats:
        s = df[f]
        n_nan = s.isna().sum()
        nan_pct = 100 * n_nan / len(df)
        flag = "  ⚠ >20% NaN" if nan_pct > 20 else ""
        print(f"  {f:<22} NaN {n_nan}/{len(df)} ({nan_pct:.1f}%)  "
              f"min={s.min():.2f} max={s.max():.2f} "
              f"mean={s.mean():.2f} std={s.std():.2f}{flag}")

    if "landcover" in df.columns:
        lc = df["landcover"].dropna().astype(int).value_counts().sort_index()
        print(f"[{label}] IGBP class counts: {dict(lc)}")

    return df, new_feats


asia, _ = enrich(PROC / "training_features.parquet",
                 PROC / "training_features_v2.parquet",
                 label="ASIA")
us, _ = enrich(PROC / "us_validation_features.parquet",
               PROC / "us_validation_features_v2.parquet",
               label="US")
