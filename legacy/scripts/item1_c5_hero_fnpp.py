"""Item 1 Checkpoint 5 — F+NPP hero map for Asia 5km.

Pipeline:
  1. Sample MODIS rasters (npp, lst_day, lst_night) at every cell of
     data/processed/asia_grid_5km.parquet. The grid is 5.58M cells.
     We use vectorized index lookup since the MODIS rasters are at
     the same 0.05° resolution as the grid.
  2. Train F+NPP and the climate-only F baseline on the v2 training
     set (after-MODIS-NaN-drop n=463).
  3. Predict both on the grid; compute anomaly = exp(F+NPP) / exp(F_baseline).
  4. Render hero with src/hero_map.render_hero_map using the existing
     model_label / model_subtitle hooks from Round C.

Outputs:
  data/processed/asia_grid_5km_v2.parquet
  data/processed/asia_predictions_F_NPP.parquet
  data/processed/hero_climate_npp_asia_anomaly.parquet
  data/outputs/hero_climate_npp_asia.{png,pdf,screen.png}
"""
import json
import sys
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hero_map import render_hero_map  # noqa: E402

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "outputs"

TARGET = "log_rs_annual"
F_PLUS_NPP = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17",
              "npp", "lst_day", "lst_night", "lst_diurnal_range"]
F_BASELINE = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
PARAMS = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
              subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
              reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0)


def sample_at(raster_path, lons, lats):
    with rasterio.open(raster_path) as src:
        coords = list(zip(lons, lats))
        vals = np.array([v[0] for v in src.sample(coords)], dtype="float64")
        nd = src.nodata
        if nd is not None:
            vals = np.where(vals == nd, np.nan, vals)
    return vals


def main() -> int:
    print("Step 1: load grid and sample MODIS")
    grid = pd.read_parquet(PROC / "asia_grid_5km.parquet")
    print(f"  grid shape: {grid.shape}")
    lons = grid["longitude"].to_numpy()
    lats = grid["latitude"].to_numpy()

    for var, fn in [("npp", "npp_2020_2024_mean.tif"),
                    ("lst_day", "lst_day_2020_2024_mean.tif"),
                    ("lst_night", "lst_night_2020_2024_mean.tif")]:
        print(f"  sampling {var}...")
        grid[var] = sample_at(RAW / "modis" / fn, lons, lats)
    grid["lst_diurnal_range"] = grid["lst_day"] - grid["lst_night"]

    grid_v2_path = PROC / "asia_grid_5km_v2.parquet"
    grid.to_parquet(grid_v2_path, index=False)
    print(f"  wrote {grid_v2_path.name}  shape={grid.shape}")
    print(f"  NPP NaN: {grid['npp'].isna().sum()/len(grid)*100:.1f}% (high — over no-vegetation)")
    print(f"  lst_day NaN: {grid['lst_day'].isna().sum()/len(grid)*100:.1f}%")

    print("\nStep 2: train F+NPP and F baseline on v2 training set")
    asia = pd.read_parquet(PROC / "training_features_v2.parquet")
    a = asia.dropna(subset=[TARGET] + F_PLUS_NPP).reset_index(drop=True)
    print(f"  train n = {len(a)}")
    X_fnpp = a[F_PLUS_NPP].to_numpy("float32")
    X_fb = a[F_BASELINE].to_numpy("float32")
    y = a[TARGET].to_numpy("float32")

    m_fnpp = xgb.XGBRegressor(**PARAMS)
    m_fnpp.fit(X_fnpp, y)
    m_fb = xgb.XGBRegressor(**PARAMS)
    m_fb.fit(X_fb, y)

    print("\nStep 3: predict on grid, compute anomaly")
    valid_fnpp = grid[F_PLUS_NPP].notna().all(axis=1).to_numpy()
    valid_fb = grid[F_BASELINE].notna().all(axis=1).to_numpy()
    pred_fnpp = np.full(len(grid), np.nan, dtype="float32")
    pred_fb = np.full(len(grid), np.nan, dtype="float32")
    chunk = 500_000
    idx_fnpp = np.where(valid_fnpp)[0]
    idx_fb = np.where(valid_fb)[0]
    for s in range(0, len(idx_fnpp), chunk):
        sl = idx_fnpp[s:s + chunk]
        pred_fnpp[sl] = m_fnpp.predict(grid.iloc[sl][F_PLUS_NPP].to_numpy("float32"))
    for s in range(0, len(idx_fb), chunk):
        sl = idx_fb[s:s + chunk]
        pred_fb[sl] = m_fb.predict(grid.iloc[sl][F_BASELINE].to_numpy("float32"))

    anom = np.exp(pred_fnpp - pred_fb)
    print(f"  anomaly stats: median={np.nanmedian(anom):.3f}, "
          f"IQR=({np.nanquantile(anom,.25):.3f},{np.nanquantile(anom,.75):.3f}), "
          f"valid frac={np.isfinite(anom).mean()*100:.1f}%")

    pred_path = PROC / "asia_predictions_F_NPP.parquet"
    pd.DataFrame({
        "longitude": grid["longitude"], "latitude": grid["latitude"],
        "log_rs_pred_fnpp": pred_fnpp, "log_rs_pred_climate_baseline": pred_fb,
        "rs_pred_fnpp": np.exp(pred_fnpp), "rs_climate_baseline": np.exp(pred_fb),
    }).to_parquet(pred_path, index=False)
    print(f"  wrote {pred_path.name}")

    anom_path = PROC / "hero_climate_npp_asia_anomaly.parquet"
    pd.DataFrame({
        "longitude": grid["longitude"], "latitude": grid["latitude"],
        "mshi_geo_anomaly": anom,
    }).to_parquet(anom_path, index=False)
    print(f"  wrote {anom_path.name}")

    print("\nStep 4: render hero")
    fnpp_metrics = json.load(open(OUT / "F_NPP_metrics.json"))
    metadata = {
        "cv_r2": round(fnpp_metrics["cv"]["mean_r2"], 3),
        "transfer_r2": round(fnpp_metrics["transfer"]["r2"], 3),
        "n_train": fnpp_metrics["n_train"],
        "n_us": fnpp_metrics["n_us"],
        "resolution_km": "~5",
        "date": datetime.date.today().isoformat(),
    }
    df_anom = pd.read_parquet(anom_path)
    render_hero_map(
        df_anom,
        OUT / "hero_climate_npp_asia.png",
        OUT / "hero_climate_npp_asia.pdf",
        OUT / "hero_climate_npp_asia_screen.png",
        metadata=metadata,
        model_label="CLIMATE + NPP MODEL",
        model_subtitle="Adds MODIS satellite vegetation productivity — best transfer of any config",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
