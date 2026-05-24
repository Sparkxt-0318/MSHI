"""Phase 3 of atlas-figure-regen-2026:
generate validation scatter plots for F+NPP and Full+MODIS models.

The previous `data/outputs/validation_scatter.png` showed R²=-0.017,
n=264 — neither F+NPP nor Full+MODIS. It came from an older v1 model
that no longer matches any current config and is renamed to
`validation_scatter_legacy.png`.

This script makes three figures:
  validation_scatter_fnpp.png       — F+NPP (n_us=223, R²=+0.145)
  validation_scatter_fullmodis.png  — Full+MODIS (n_us=223, R²=+0.072)
  validation_scatter_comparison.png — side-by-side, shared axes

No model retraining: loads pre-trained
  data/outputs/F_NPP_model.json
  data/outputs/Full_MODIS_model.json
and predicts on
  data/processed/us_validation_features_v2.parquet
"""
import json
import sys
import datetime
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

TARGET = "log_rs_annual"
LC_CLASSES = [2, 4, 5, 8, 9, 10, 12, 13, 14, 17]  # from Full_MODIS_metrics.json


def add_lc_onehot(df):
    out = df.copy()
    for c in LC_CLASSES:
        out[f"lc_{c:02d}"] = (out["landcover"].astype("Int64") == c).astype("float32")
    return out


def predict_held_out(model_path: Path, features: list, us: pd.DataFrame):
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    clean = us.dropna(subset=[TARGET] + features).reset_index(drop=True)
    X = clean[features].to_numpy("float32")
    y = clean[TARGET].to_numpy("float32")
    pred = model.predict(X)
    return y, pred, len(clean)


def make_scatter(ax, y, pred, title, subtitle):
    lo = float(min(y.min(), pred.min())) - 0.1
    hi = float(max(y.max(), pred.max())) + 0.1
    ax.plot([lo, hi], [lo, hi], "k--", lw=1.0, alpha=0.55)
    ax.scatter(y, pred, s=18, alpha=0.55,
               color="#3B7DBE", edgecolor="none")
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("observed log Rs annual", fontsize=10)
    ax.set_ylabel("predicted log Rs annual", fontsize=10)
    ax.set_title(f"{title}\n{subtitle}", fontsize=11)
    ax.tick_params(labelsize=9)


def main() -> int:
    fnpp_meta = json.loads((OUT / "F_NPP_metrics.json").read_text())
    full_meta = json.loads((OUT / "Full_MODIS_metrics.json").read_text())

    us = pd.read_parquet(PROC / "us_validation_features_v2.parquet")
    us = add_lc_onehot(us)

    fnpp_feats = fnpp_meta["features"]
    full_feats = full_meta["features"]

    print(f"F+NPP features (n={len(fnpp_feats)}): {fnpp_feats}")
    print(f"Full+MODIS features (n={len(full_feats)})")

    y_fnpp, p_fnpp, n_fnpp = predict_held_out(
        OUT / "F_NPP_model.json", fnpp_feats, us)
    y_full, p_full, n_full = predict_held_out(
        OUT / "Full_MODIS_model.json", full_feats, us)

    r2_fnpp = r2_score(y_fnpp, p_fnpp)
    r2_full = r2_score(y_full, p_full)
    rmse_fnpp = float(np.sqrt(mean_squared_error(y_fnpp, p_fnpp)))
    rmse_full = float(np.sqrt(mean_squared_error(y_full, p_full)))

    print(f"F+NPP       : n={n_fnpp}  R²={r2_fnpp:+.4f}  RMSE={rmse_fnpp:.3f}")
    print(f"Full+MODIS  : n={n_full}  R²={r2_full:+.4f}  RMSE={rmse_full:.3f}")

    # Sanity-check against the metrics files.
    expected_fnpp = fnpp_meta["transfer"]["r2"]
    expected_full = full_meta["transfer"]["r2"]
    assert abs(r2_fnpp - expected_fnpp) < 1e-3, (
        f"F+NPP R² mismatch: got {r2_fnpp:.4f}, expected {expected_fnpp:.4f}")
    assert abs(r2_full - expected_full) < 1e-3, (
        f"Full+MODIS R² mismatch: got {r2_full:.4f}, expected {expected_full:.4f}")
    assert n_fnpp == fnpp_meta["n_us"], (
        f"F+NPP n mismatch: got {n_fnpp}, expected {fnpp_meta['n_us']}")
    assert n_full == full_meta["n_us"], (
        f"Full+MODIS n mismatch: got {n_full}, expected {full_meta['n_us']}")
    print("source-of-truth sanity check passed")

    # 2a. F+NPP scatter
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    make_scatter(
        ax, y_fnpp, p_fnpp,
        "F+NPP: Asia → US transfer",
        "R² = +0.145, 95% CI (+0.026, +0.241), n = 223",
    )
    plt.tight_layout()
    out1 = OUT / "validation_scatter_fnpp.png"
    fig.savefig(out1, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"  → {out1}")

    # 2b. Full+MODIS scatter
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    make_scatter(
        ax, y_full, p_full,
        "Full+MODIS: Asia → US transfer",
        "R² = +0.072, 95% CI (-0.084, +0.189), n = 223 — CI spans zero",
    )
    plt.tight_layout()
    out2 = OUT / "validation_scatter_fullmodis.png"
    fig.savefig(out2, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"  → {out2}")

    # 2c. Comparison panel (shared axes)
    all_lo = float(min(y_fnpp.min(), p_fnpp.min(), y_full.min(), p_full.min())) - 0.1
    all_hi = float(max(y_fnpp.max(), p_fnpp.max(), y_full.max(), p_full.max())) + 0.1

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.8),
                             gridspec_kw={"wspace": 0.18})
    for ax in axes:
        ax.plot([all_lo, all_hi], [all_lo, all_hi], "k--", lw=1.0, alpha=0.55)
        ax.set_xlim(all_lo, all_hi); ax.set_ylim(all_lo, all_hi)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("observed log Rs annual", fontsize=10)
        ax.tick_params(labelsize=9)
    axes[0].scatter(y_fnpp, p_fnpp, s=18, alpha=0.55,
                    color="#3B7DBE", edgecolor="none")
    axes[0].set_ylabel("predicted log Rs annual", fontsize=10)
    axes[0].set_title("F+NPP: 8 bioclim + 4 MODIS\n"
                      "R² = +0.145, 95% CI (+0.026, +0.241), n = 223",
                      fontsize=10.5)
    axes[1].scatter(y_full, p_full, s=18, alpha=0.55,
                    color="#A4221A", edgecolor="none")
    axes[1].set_title("Full+MODIS: 34 features\n"
                      "R² = +0.072, 95% CI (-0.084, +0.189), n = 223  — CI spans 0",
                      fontsize=10.5)
    fig.suptitle("Held-out US validation — adding features hurts transfer",
                 fontsize=13, y=0.99)
    plt.tight_layout(rect=(0, 0, 1, 0.95))
    out3 = OUT / "validation_scatter_comparison.png"
    fig.savefig(out3, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"  → {out3}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
