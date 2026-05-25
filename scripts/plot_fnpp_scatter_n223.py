"""Render the F+NPP (climate + MODIS NPP) transfer-validation scatter
plot for the held-out US test set (n=223), saved to
figures/validation_scatter_fnpp_n223.png at 300 DPI.

Loads the pre-trained F_NPP XGBoost model from data/outputs and predicts
on data/processed/us_validation_features_v2.parquet. Performs a NaN
audit before prediction so the row count and which columns drove any
drops are explicit.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"

TARGET = "log_rs_annual"
MODEL_PATH = OUT / "F_NPP_model.json"
META_PATH = OUT / "F_NPP_metrics.json"
US_PATH = PROC / "us_validation_features_v2.parquet"
FIG_PATH = FIG / "validation_scatter_fnpp_n223.png"


def main() -> int:
    meta = json.loads(META_PATH.read_text())
    features = meta["features"]
    print(f"Loaded F+NPP config (config key: F_NPP / climate_npp).")
    print(f"  features (n={len(features)}): {features}")

    us = pd.read_parquet(US_PATH)
    print(f"  US validation rows pre-filter: {len(us)}")

    needed_cols = [TARGET] + features
    missing_cols = [c for c in needed_cols if c not in us.columns]
    if missing_cols:
        raise RuntimeError(f"missing columns in US parquet: {missing_cols}")

    # NaN audit: count how many rows are dropped and which columns drive it.
    pre_n = len(us)
    null_mask = us[needed_cols].isna()
    drop_mask = null_mask.any(axis=1)
    if drop_mask.any():
        per_col_nan = null_mask.sum().to_dict()
        per_col_nan = {k: int(v) for k, v in per_col_nan.items() if v > 0}
        print("  NaN audit — rows dropped due to NaN in:")
        for col, n in sorted(per_col_nan.items(), key=lambda kv: -kv[1]):
            print(f"    {col}: {n} NaN")
        dropped_idx = us.index[drop_mask].tolist()
        print(f"  dropped row indices (first 20 of {len(dropped_idx)}): "
              f"{dropped_idx[:20]}")

    clean = us.dropna(subset=needed_cols).reset_index(drop=True)
    n = len(clean)
    print(f"  US validation rows post-filter: {n} (dropped {pre_n - n})")

    model = xgb.XGBRegressor()
    model.load_model(str(MODEL_PATH))

    X = clean[features].to_numpy("float32")
    y = clean[TARGET].to_numpy("float32")
    pred = model.predict(X)

    r2 = float(r2_score(y, pred))
    rmse = float(np.sqrt(mean_squared_error(y, pred)))
    print(f"  metrics: n={n}  R2={r2:+.4f}  RMSE={rmse:.3f}")

    # Plot.
    FIG.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 6.5), facecolor="white")
    ax.set_facecolor("white")

    lo = float(min(y.min(), pred.min())) - 0.1
    hi = float(max(y.max(), pred.max())) + 0.1
    ax.plot([lo, hi], [lo, hi], linestyle="--", color="gray",
            lw=1.0, alpha=0.7, label="1:1")
    ax.scatter(y, pred, s=22, alpha=0.6, color="#3B7DBE",
               edgecolor="none")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("observed log Rs annual", fontsize=11)
    ax.set_ylabel("predicted log Rs annual", fontsize=11)
    ax.set_title(
        f"F+NPP: Asia → US transfer\n"
        f"R² = {r2:.3f},  RMSE = {rmse:.3f},  n = {n}",
        fontsize=12,
    )
    ax.tick_params(labelsize=10)

    fig.tight_layout()
    fig.savefig(FIG_PATH, dpi=300, facecolor="white")
    plt.close(fig)
    print(f"  saved -> {FIG_PATH.relative_to(ROOT)}")

    # Confirmation against the spec (R2=0.145, n=223).
    print()
    print("=== confirmation ===")
    print(f"n     = {n}     (expected 223)  {'OK' if n == 223 else 'MISMATCH'}")
    print(f"R^2   = {r2:.3f}  (expected 0.145)  "
          f"{'OK' if abs(r2 - 0.145) < 1e-3 else 'MISMATCH'}")
    return 0 if (n == 223 and abs(r2 - 0.145) < 1e-3) else 1


if __name__ == "__main__":
    raise SystemExit(main())
