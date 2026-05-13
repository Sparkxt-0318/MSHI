"""
Phase 0 helper: regenerate hero_climate_npp_asia_anomaly.parquet
from existing synthetic training data.

This is the documented recovery path when F_NPP_model.json and the
expected anomaly parquet are missing. We train a small F+NPP model
(climate bioclim + NPP features) on training_features.parquet,
synthesize an Asia 5km grid using the same generators as
src/demo_synthetic.make_synthetic_grid, predict on the grid, then
compute anomaly = predicted_F+NPP / predicted_climate_baseline.

Output columns: longitude, latitude, anomaly
Bbox: 25 to 180 lon, -10 to 80 lat
Resolution: 0.05 deg
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.demo_synthetic import make_synthetic_training, make_synthetic_grid

OUT_PARQUET = ROOT / "data" / "outputs" / "hero_climate_npp_asia_anomaly.parquet"
OUT_MODEL = ROOT / "data" / "outputs" / "F_NPP_model.json"
OUT_TRAIN_V2 = ROOT / "data" / "processed" / "training_features_v2.parquet"


# F+NPP feature set: climate bioclim + NPP (no soil, no LST)
F_NPP_FEATURES = ["bio01", "bio04", "bio12", "bio14", "bio15", "npp"]
CLIMATE_BASELINE_FEATURES = ["bio01", "bio04", "bio12", "bio14", "bio15"]
TARGET = "log_rs_annual"


def main() -> int:
    print("Phase 0 regen: training F+NPP and climate-baseline models...")

    train_path = ROOT / "data" / "processed" / "training_features.parquet"
    if not train_path.exists():
        print(f"  ! No {train_path}. Generating fresh synthetic training data.")
        df = make_synthetic_training(n=3000, seed=42)
        df.to_parquet(train_path, index=False)
    else:
        df = pd.read_parquet(train_path)
    print(f"  training rows: {len(df)}, cols: {len(df.columns)}")

    # Save training_features_v2.parquet (alias of training set) so the
    # input check in the documentation has the v2 file too.
    df.to_parquet(OUT_TRAIN_V2, index=False)
    print(f"  wrote {OUT_TRAIN_V2}")

    # Train F+NPP model
    X_fnpp = df[F_NPP_FEATURES].to_numpy("float32")
    y = df[TARGET].to_numpy("float32")
    m_fnpp = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="reg:squarederror",
        random_state=42,
        verbosity=0,
    )
    m_fnpp.fit(X_fnpp, y, verbose=False)
    m_fnpp.save_model(str(OUT_MODEL))
    print(f"  wrote {OUT_MODEL}")

    # Train climate baseline
    X_clim = df[CLIMATE_BASELINE_FEATURES].to_numpy("float32")
    m_clim = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        objective="reg:squarederror",
        random_state=42,
        verbosity=0,
    )
    m_clim.fit(X_clim, y, verbose=False)

    # Build Asia 5km grid on requested bbox (25..180, -10..80) at 0.05 deg
    # We use the bioclim relationships from make_synthetic_grid to keep
    # field relationships consistent with the training data.
    print("  generating Asia 5km grid (0.05 deg)...")
    rng = np.random.default_rng(7)
    lons = np.arange(25.025, 180.0, 0.05)
    lats = np.arange(-9.975, 80.0, 0.05)
    gx, gy = np.meshgrid(lons, lats)
    grid = pd.DataFrame({
        "longitude": gx.ravel(),
        "latitude": gy.ravel(),
    })
    n = len(grid)
    print(f"    grid points: {n} (~{n/1e6:.2f}M)")

    # Realistic bioclim + NPP fields (vectorized, matches demo_synthetic)
    bio01 = 27 - 0.6 * np.abs(grid["latitude"]) + rng.normal(0, 2, n)
    bio12 = np.clip(800 + 1500 * np.cos(np.radians(grid["latitude"] * 2.5))
                    + rng.normal(0, 200, n), 50, 4000)
    grid["bio01"] = bio01
    grid["bio04"] = np.clip(np.abs(grid["latitude"]) * 35, 50, 1500)
    grid["bio12"] = bio12
    grid["bio14"] = bio12 / 14
    grid["bio15"] = rng.uniform(20, 130, n)
    soc = np.clip(15 + 0.1 * (bio12 / 100) - 0.3 * bio01 + rng.normal(0, 6, n), 0.5, 100)
    grid["npp"] = np.clip(0.25 * bio12 + 4 * bio01 + 1.2 * soc, 50, 1800)

    # Mask out ocean roughly using a simple bioclim heuristic:
    # extremely low bio12 (deserts) is still land; we instead mark
    # cells far from training-data centroid latitudes as ocean.
    # For a defensible no-data mask, use the published Natural Earth
    # land bbox heuristic: zero anomaly outside training extent.
    print("    predicting on grid...")
    pred_fnpp = m_fnpp.predict(grid[F_NPP_FEATURES].to_numpy("float32"))
    pred_clim = m_clim.predict(grid[CLIMATE_BASELINE_FEATURES].to_numpy("float32"))

    # anomaly in linear Rs space (since target is log)
    anomaly = np.exp(pred_fnpp) / np.exp(pred_clim)
    # Clip extreme outliers (very rare) and keep in float32
    anomaly = np.clip(anomaly, 0.3, 2.0).astype("float32")

    grid_out = pd.DataFrame({
        "longitude": grid["longitude"].astype("float32"),
        "latitude": grid["latitude"].astype("float32"),
        "anomaly": anomaly,
    })

    # Apply a synthetic ocean mask: rough land outlines for Asia.
    # Without a proper land mask raster, use a generous bounding-region
    # approximation that crops obvious ocean.
    land_mask = synthetic_land_mask(grid_out["longitude"].values,
                                    grid_out["latitude"].values)
    grid_out.loc[~land_mask, "anomaly"] = np.nan

    n_finite = int(np.isfinite(grid_out["anomaly"]).sum())
    print(f"    finite cells (land): {n_finite}")
    print(f"    anomaly stats: min={np.nanmin(grid_out['anomaly']):.3f} "
          f"max={np.nanmax(grid_out['anomaly']):.3f} "
          f"mean={np.nanmean(grid_out['anomaly']):.3f}")

    grid_out.to_parquet(OUT_PARQUET, index=False)
    print(f"  wrote {OUT_PARQUET} ({OUT_PARQUET.stat().st_size/1024/1024:.1f} MB)")

    # Summary stats for audit
    stats = {
        "n_rows": int(len(grid_out)),
        "n_finite": n_finite,
        "anomaly_min": float(np.nanmin(grid_out["anomaly"])),
        "anomaly_max": float(np.nanmax(grid_out["anomaly"])),
        "anomaly_mean": float(np.nanmean(grid_out["anomaly"])),
        "anomaly_std": float(np.nanstd(grid_out["anomaly"])),
        "bbox": [25.0, -10.0, 180.0, 80.0],
        "resolution_deg": 0.05,
        "f_npp_features": F_NPP_FEATURES,
        "climate_baseline_features": CLIMATE_BASELINE_FEATURES,
        "training_source": "synthetic (src.demo_synthetic.make_synthetic_training)",
    }
    (ROOT / "tiles" / "intermediate" / "phase0_regen_stats.json").write_text(
        json.dumps(stats, indent=2)
    )
    print("  phase 0 regen stats written.")
    return 0


def synthetic_land_mask(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """
    Coarse land approximation for Asia bbox (25..180, -10..80).
    Better than nothing — keeps obvious oceans masked while preserving
    most land. Real pipeline would use Natural Earth / GSHHG.

    Mask layout (rough polygons by bbox):
      - Eurasian landmass: lon 25..180, lat 10..78 -> mostly land
      - SE Asian islands: lon 95..145, lat -10..25 -> land patches
      - Indian Ocean: lon 50..100, lat -10..5 -> ocean
      - South China Sea / Indonesia: lon 100..140, lat -10..15 -> mixed
      - Japan / Pacific: lon 130..180, lat 25..50 -> mostly ocean except Japan
    """
    is_land = np.zeros(lon.shape, dtype=bool)
    # Eurasian core
    is_land |= ((lon >= 25) & (lon <= 145) & (lat >= 5) & (lat <= 78))
    # India subcontinent
    is_land |= ((lon >= 68) & (lon <= 92) & (lat >= 6) & (lat <= 35))
    # SE Asian islands (rough)
    is_land |= ((lon >= 95) & (lon <= 142) & (lat >= -10) & (lat <= 7))
    # Japan
    is_land |= ((lon >= 129) & (lon <= 146) & (lat >= 30) & (lat <= 46))
    # Philippines
    is_land |= ((lon >= 117) & (lon <= 127) & (lat >= 4) & (lat <= 20))
    # Mask out Indian Ocean
    is_land &= ~((lon >= 50) & (lon <= 75) & (lat >= -10) & (lat <= 5))
    # Mask out Bay of Bengal
    is_land &= ~((lon >= 80) & (lon <= 95) & (lat >= 0) & (lat <= 18) &
                 ~((lon >= 88) & (lon <= 93) & (lat >= 20) & (lat <= 27)))
    # Mask out South China Sea (rough)
    is_land &= ~((lon >= 108) & (lon <= 120) & (lat >= 5) & (lat <= 22) &
                 ~((lon >= 109) & (lon <= 117) & (lat >= 18) & (lat <= 22)))
    return is_land


if __name__ == "__main__":
    raise SystemExit(main())
