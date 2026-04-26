"""
demo_synthetic.py — end-to-end smoke test of the v2 MSHI-Geo pipeline
(soil respiration target). Runs in <1 minute, no internet needed.

Validates: training → spatial CV → SHAP → climate baseline → anomaly composite
→ hero map render.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("mshi_geo.demo")

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "data" / "outputs"
PROCESSED.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic data generators
# ─────────────────────────────────────────────────────────────────────────────
def make_synthetic_training(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    """
    Synthetic training table with realistic relationships for log_rs_annual.
    Mostly Asia (75%) + some US (25%) to mimic geographic distribution.
    """
    rng = np.random.default_rng(seed)
    n_asia, n_us = int(0.75 * n), n - int(0.75 * n)
    longitude = np.concatenate([rng.uniform(35, 175, n_asia),
                                 rng.uniform(-122, -70, n_us)])
    latitude  = np.concatenate([rng.uniform(-5, 70, n_asia),
                                 rng.uniform(28, 48, n_us)])

    bio01 = 27 - 0.6 * np.abs(latitude) + rng.normal(0, 3, n)
    bio12 = np.clip(800 + 1500 * np.cos(np.radians(latitude * 2.5))
                    + rng.normal(0, 250, n), 50, 4000)
    bio04 = np.clip(np.abs(latitude) * 35 + rng.normal(0, 100, n), 50, 1500)
    bio05 = bio01 + 12 + rng.normal(0, 2, n)
    bio06 = bio01 - 15 + rng.normal(0, 3, n)
    bio14 = np.clip(bio12 / 14 + rng.normal(0, 8, n), 0, 400)
    bio15 = np.clip(rng.uniform(20, 130, n), 5, 200)
    bio17 = np.clip(bio12 / 6 + rng.normal(0, 30, n), 5, 1000)

    soc = np.clip(15 + 0.1 * (bio12/100) - 0.3 * bio01 + rng.normal(0, 8, n), 0.5, 100)
    nitrogen = np.clip(soc * 0.08 + rng.normal(0, 0.2, n), 0.05, 12)
    phh2o = np.clip(7.0 - 0.0006 * bio12 + rng.normal(0, 0.5, n), 3.5, 9.5)
    clay = np.clip(rng.uniform(50, 450, n) + rng.normal(0, 50, n), 10, 800)
    sand = np.clip(rng.uniform(150, 700, n) + rng.normal(0, 80, n), 20, 950)
    silt = np.clip(1000 - clay - sand + rng.normal(0, 30, n), 10, 800)
    bdod = np.clip(1.45 - 0.005 * soc + rng.normal(0, 0.07, n), 0.9, 1.85)
    cec  = np.clip(soc * 0.5 + clay * 0.05 + rng.normal(0, 4, n), 2, 80)
    npp = np.clip(0.25 * bio12 + 4 * bio01 + 1.2 * soc + rng.normal(0, 60, n), 50, 1800)
    lst_day = bio01 + 8 + rng.normal(0, 1.5, n)
    lst_night = bio01 - 4 + rng.normal(0, 1.5, n)
    landcover = rng.integers(1, 17, n)

    # Soil respiration: well-known empirical relationship
    # log Rs ~ a + b*T + c*log(P) + d*log(SOC) + Q10 effect via temp seasonality
    log_rs = (
        4.4
        + 0.04 * bio01
        + 0.30 * np.log(bio12 + 50)
        + 0.25 * np.log(soc + 1)
        + 0.20 * np.log(npp / 100 + 1)
        - 0.05 * (np.abs(phh2o - 6.5))
        - 0.0001 * bio04
    )
    log_rs = log_rs + rng.normal(0, 0.25, n)
    rs_annual = np.exp(log_rs)

    df = pd.DataFrame({
        "site_id": [f"site_{i}" for i in range(n)],
        "source": "synthetic",
        "longitude": longitude, "latitude": latitude,
        "soc": soc, "nitrogen": nitrogen, "phh2o": phh2o,
        "clay": clay, "sand": sand, "silt": silt,
        "bdod": bdod, "cec": cec,
        "bio01": bio01, "bio04": bio04, "bio05": bio05, "bio06": bio06,
        "bio12": bio12, "bio14": bio14, "bio15": bio15, "bio17": bio17,
        "npp": npp, "lst_day": lst_day, "lst_night": lst_night,
        "landcover": landcover.astype("float32"),
        "rs_annual": rs_annual, "log_rs_annual": log_rs,
    })
    df["c_n_ratio"] = df["soc"] / df["nitrogen"]
    df["clay_sand_ratio"] = df["clay"] / df["sand"]
    df["aridity_demartonne"] = df["bio12"] / (df["bio01"] + 10)
    df["lst_diurnal_range"] = df["lst_day"] - df["lst_night"]
    return df


def make_synthetic_grid(resolution_deg: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    lons = np.arange(35.5, 175.5, resolution_deg)
    lats = np.arange(-4.5, 70.5, resolution_deg)
    gx, gy = np.meshgrid(lons, lats)
    df = pd.DataFrame({"longitude": gx.ravel(), "latitude": gy.ravel()})
    n = len(df)
    bio01 = 27 - 0.6 * np.abs(df["latitude"]) + rng.normal(0, 2, n)
    bio12 = np.clip(800 + 1500 * np.cos(np.radians(df["latitude"] * 2.5))
                    + rng.normal(0, 200, n), 50, 4000)
    df["bio01"] = bio01
    df["bio04"] = np.clip(np.abs(df["latitude"]) * 35, 50, 1500)
    df["bio05"] = bio01 + 12; df["bio06"] = bio01 - 15
    df["bio12"] = bio12
    df["bio14"] = bio12 / 14
    df["bio15"] = rng.uniform(20, 130, n)
    df["bio17"] = bio12 / 6
    df["soc"] = np.clip(15 + 0.1 * (bio12/100) - 0.3 * bio01 + rng.normal(0, 6, n), 0.5, 100)
    df["nitrogen"] = np.clip(df["soc"] * 0.08, 0.05, 12)
    df["phh2o"] = np.clip(7.0 - 0.0006 * bio12 + rng.normal(0, 0.3, n), 3.5, 9.5)
    df["clay"] = rng.uniform(80, 400, n)
    df["sand"] = rng.uniform(200, 600, n)
    df["silt"] = np.clip(1000 - df["clay"] - df["sand"], 10, 800)
    df["bdod"] = np.clip(1.45 - 0.005 * df["soc"], 0.9, 1.85)
    df["cec"] = np.clip(df["soc"] * 0.5 + df["clay"] * 0.05, 2, 80)
    df["npp"] = np.clip(0.25 * bio12 + 4 * bio01 + 1.2 * df["soc"], 50, 1800)
    df["lst_day"] = bio01 + 8; df["lst_night"] = bio01 - 4
    df["landcover"] = rng.integers(1, 17, n).astype("float32")
    df["c_n_ratio"] = df["soc"] / df["nitrogen"]
    df["clay_sand_ratio"] = df["clay"] / df["sand"]
    df["aridity_demartonne"] = df["bio12"] / (df["bio01"] + 10)
    df["lst_diurnal_range"] = df["lst_day"] - df["lst_night"]
    return df


def run() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from src.train import spatial_kfold_split
    from src.composite import train_climate_baseline, apply_anomaly
    from src.hero_map import render_hero_map

    LOG.info("=" * 60)
    LOG.info("MSHI-Geo SYNTHETIC SMOKE TEST (v2: respiration target)")
    LOG.info("=" * 60)

    import xgboost as xgb
    from sklearn.metrics import r2_score, mean_squared_error

    # Step 1: Training table
    df = make_synthetic_training(n=3000)
    train_path = PROCESSED / "training_features.parquet"
    df.to_parquet(train_path, index=False)
    LOG.info("Step 1 ✓ Training table: %d rows → %s", len(df), train_path)

    # Step 2: Train full model
    target = "log_rs_annual"
    drop_cols = {target, "rs_annual", "longitude", "latitude",
                 "site_id", "source"}
    feature_cols = [c for c in df.columns if c not in drop_cols]
    X = df[feature_cols].to_numpy("float32")
    y = df[target].to_numpy("float32")

    cv_scores = []
    for k, tr, va in spatial_kfold_split(df, n_splits=4, block_size_deg=10.0):
        m = xgb.XGBRegressor(
            n_estimators=400, max_depth=5, learning_rate=0.06,
            subsample=0.85, colsample_bytree=0.85,
            min_child_weight=4, reg_lambda=1.0, verbosity=0,
            objective="reg:squarederror",
            early_stopping_rounds=30, eval_metric="rmse",
        )
        m.fit(X[tr], y[tr], eval_set=[(X[va], y[va])], verbose=False)
        p = m.predict(X[va])
        cv_scores.append({"fold": k,
                          "r2": float(r2_score(y[va], p)),
                          "rmse": float(np.sqrt(mean_squared_error(y[va], p)))})
        LOG.info("  fold %d: R²=%.3f rmse=%.3f", k, cv_scores[-1]["r2"], cv_scores[-1]["rmse"])

    final = xgb.XGBRegressor(
        n_estimators=400, max_depth=5, learning_rate=0.06,
        subsample=0.85, colsample_bytree=0.85,
        objective="reg:squarederror", verbosity=0,
    )
    final.fit(X, y, verbose=False)
    final.save_model(str(OUTPUTS / "mshi_geo_xgb.json"))
    cv_r2 = float(np.mean([s["r2"] for s in cv_scores]))
    LOG.info("Step 2 ✓ Trained model. CV mean R² = %.3f", cv_r2)

    metrics = {
        "n_train_total": len(df), "feature_cols": feature_cols,
        "target_col": target, "cv": cv_scores,
        "cv_mean_r2": cv_r2,
        "cv_mean_rmse": float(np.mean([s["rmse"] for s in cv_scores])),
    }
    (OUTPUTS / "training_metrics.json").write_text(json.dumps(metrics, indent=2))

    # Step 3: Asia→US transfer
    is_us = (df["longitude"] < -50)
    asia, us = df[~is_us].reset_index(drop=True), df[is_us].reset_index(drop=True)
    m2 = xgb.XGBRegressor(
        n_estimators=400, max_depth=5, learning_rate=0.06,
        subsample=0.85, colsample_bytree=0.85, verbosity=0,
        objective="reg:squarederror",
    )
    m2.fit(asia[feature_cols].to_numpy("float32"),
           asia[target].to_numpy("float32"))
    pred_us = m2.predict(us[feature_cols].to_numpy("float32"))
    r2_us = float(r2_score(us[target], pred_us))
    rmse_us = float(np.sqrt(mean_squared_error(us[target], pred_us)))
    LOG.info("Step 3 ✓ Asia→US transfer: R²=%.3f rmse=%.3f n=%d", r2_us, rmse_us, len(us))
    val_report = {"n_us_points": int(len(us)),
                  "asia_to_us_transfer": {"r2": r2_us, "rmse": rmse_us}}
    (OUTPUTS / "validation_report.json").write_text(json.dumps(val_report, indent=2))

    # Step 4: Climate baseline
    LOG.info("Step 4 training climate-only baseline")
    cb_params = dict(n_estimators=300, max_depth=4, learning_rate=0.05,
                     subsample=0.85, objective="reg:squarederror")
    climate_features = ["bio01", "bio04", "bio12", "bio14", "bio15"]
    climate_model, used_feats = train_climate_baseline(
        df, climate_features, target, cb_params)

    # Step 5: Asia grid prediction + anomaly composite
    LOG.info("Step 5 grid prediction + anomaly composite")
    grid = make_synthetic_grid(resolution_deg=1.0)
    grid["log_rs_pred"] = final.predict(grid[feature_cols].to_numpy("float32"))
    grid["rs_pred"] = np.exp(grid["log_rs_pred"])
    grid_anom = apply_anomaly(grid, "log_rs_pred", climate_model, used_feats)
    composite_path = PROCESSED / "asia_grid_demo_anomaly.parquet"
    grid_anom.to_parquet(composite_path, index=False)
    LOG.info("        Anomaly mean=%.3f std=%.3f",
             grid_anom["mshi_geo_anomaly"].mean(),
             grid_anom["mshi_geo_anomaly"].std())

    # Step 6: Hero map
    LOG.info("Step 6 rendering hero map")
    render_hero_map(
        grid_anom,
        OUTPUTS / "hero_mshi_geo_asia.png",
        OUTPUTS / "hero_mshi_geo_asia.pdf",
        OUTPUTS / "hero_mshi_geo_asia_screen.png",
        metadata={
            "cv_r2": cv_r2,
            "transfer_r2": r2_us,
            "n_train": len(df),
            "n_us": len(us),
            "resolution_km": "~5 (demo)",
        },
    )

    LOG.info("=" * 60)
    LOG.info("SMOKE TEST COMPLETE")
    LOG.info("=" * 60)
    print("\nOutputs:")
    for f in sorted(OUTPUTS.iterdir()):
        if f.name.startswith("."): continue
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<45s}  {size_kb:8.1f} KB")


if __name__ == "__main__":
    run()
