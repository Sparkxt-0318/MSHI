"""
train.py — train MSHI-Geo model with spatial block cross-validation.

Reads:
    data/processed/training_features.parquet  (Asia points + features + log_mbc)
Writes:
    data/outputs/mshi_geo_xgb.json           (trained model)
    data/outputs/training_metrics.json       (CV metrics, feature list)
    data/outputs/shap_summary.png            (SHAP feature importance)

Run:
    python src/train.py --config configs/mshi_geo.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.model_selection import KFold

LOG = logging.getLogger("mshi_geo.train")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# Spatial block CV
# ─────────────────────────────────────────────────────────────────────────────
def assign_spatial_blocks(
    df: pd.DataFrame, block_size_deg: float, lon_col="longitude", lat_col="latitude"
) -> np.ndarray:
    """Assign each point an integer block ID based on lat/lon binning."""
    lon_bin = np.floor(df[lon_col] / block_size_deg).astype(int)
    lat_bin = np.floor(df[lat_col] / block_size_deg).astype(int)
    return (lon_bin * 10_000 + lat_bin).to_numpy()


def spatial_kfold_split(
    df: pd.DataFrame, n_splits: int, block_size_deg: float, seed: int = 42
):
    """Yield (train_idx, val_idx) such that no block appears in both."""
    blocks = assign_spatial_blocks(df, block_size_deg)
    unique = np.unique(blocks)
    rng = np.random.default_rng(seed)
    rng.shuffle(unique)
    folds = np.array_split(unique, n_splits)
    for k, val_blocks in enumerate(folds):
        val_mask = np.isin(blocks, val_blocks)
        yield k, np.where(~val_mask)[0], np.where(val_mask)[0]


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────
def train_xgboost(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    cfg: Dict,
) -> Tuple[object, Dict]:
    """Fit XGBoost with spatial CV; return final model + metrics dict."""
    import xgboost as xgb

    X = df[feature_cols].to_numpy(dtype="float32")
    y = df[target_col].to_numpy(dtype="float32")

    params = dict(cfg["model"]["xgboost_params"])
    early_stop = params.pop("early_stopping_rounds", 50)

    cv_metrics = []
    if cfg["model"]["spatial_cv"]["enabled"]:
        for k, tr, va in spatial_kfold_split(
            df,
            cfg["model"]["spatial_cv"]["n_splits"],
            cfg["model"]["spatial_cv"]["block_size_deg"],
            cfg["seed"],
        ):
            model = xgb.XGBRegressor(
                **params, early_stopping_rounds=early_stop, eval_metric="rmse"
            )
            model.fit(
                X[tr], y[tr],
                eval_set=[(X[va], y[va])],
                verbose=False,
            )
            preds = model.predict(X[va])
            cv_metrics.append({
                "fold": int(k),
                "n_train": int(len(tr)),
                "n_val":   int(len(va)),
                "r2":      float(r2_score(y[va], preds)),
                "rmse":    float(np.sqrt(mean_squared_error(y[va], preds))),
                "mae":     float(mean_absolute_error(y[va], preds)),
            })
            LOG.info("Fold %d: R²=%.3f  RMSE=%.3f  MAE=%.3f  (n_val=%d)",
                     k, cv_metrics[-1]["r2"], cv_metrics[-1]["rmse"],
                     cv_metrics[-1]["mae"], len(va))

    # Final model on full data
    final = xgb.XGBRegressor(**params)
    final.fit(X, y, verbose=False)
    return final, {
        "n_train_total": int(len(df)),
        "feature_cols": feature_cols,
        "target_col": target_col,
        "cv": cv_metrics,
        "cv_mean_r2": float(np.mean([m["r2"] for m in cv_metrics])) if cv_metrics else None,
        "cv_mean_rmse": float(np.mean([m["rmse"] for m in cv_metrics])) if cv_metrics else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SHAP
# ─────────────────────────────────────────────────────────────────────────────
def compute_shap_summary(model, X: pd.DataFrame, out_path: Path) -> Dict:
    """Generate SHAP summary plot and return feature-importance ranking."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    out_path.parent.mkdir(parents=True, exist_ok=True)
    explainer = shap.TreeExplainer(model)

    # Subsample for plotting speed
    Xs = X.sample(min(2000, len(X)), random_state=42)
    sv = explainer.shap_values(Xs)

    plt.figure(figsize=(10, 7))
    shap.summary_plot(sv, Xs, show=False, max_display=20)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()

    importance = (
        pd.DataFrame({
            "feature": Xs.columns,
            "mean_abs_shap": np.abs(sv).mean(axis=0),
        })
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    return {
        "ranked_features": importance.to_dict(orient="records"),
        "shap_plot": str(out_path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main(cfg_path: Path) -> int:
    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]

    feat_path = root / cfg["paths"]["feature_table_train"]
    df = pd.read_parquet(feat_path)
    LOG.info("Loaded training table: %d rows × %d cols from %s",
             len(df), df.shape[1], feat_path)

    target = cfg["model"]["target"]
    drop_cols = {target, "rs_annual", "longitude", "latitude",
                 "site_id", "source", "region"}
    feature_cols = [c for c in df.columns if c not in drop_cols]
    df_clean = df.dropna(subset=[target] + feature_cols)
    LOG.info("After NaN drop: %d rows; %d features", len(df_clean), len(feature_cols))

    model, metrics = train_xgboost(df_clean, feature_cols, target, cfg)

    # Persist model
    model_path = root / cfg["paths"]["model"]
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    LOG.info("Saved model → %s", model_path)

    # SHAP
    shap_info = compute_shap_summary(
        model,
        df_clean[feature_cols],
        root / cfg["paths"]["shap_summary"],
    )
    metrics["shap"] = shap_info

    metrics_path = root / "data" / "outputs" / "training_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    LOG.info("Saved metrics → %s", metrics_path)

    print("\n=== TRAINING SUMMARY ===")
    print(f"  rows: {metrics['n_train_total']}")
    print(f"  features ({len(feature_cols)}): {feature_cols}")
    print(f"  CV mean R²:   {metrics['cv_mean_r2']:.3f}" if metrics["cv_mean_r2"] else "")
    print(f"  CV mean RMSE: {metrics['cv_mean_rmse']:.3f}" if metrics["cv_mean_rmse"] else "")
    print(f"  Top 5 SHAP features:")
    for row in shap_info["ranked_features"][:5]:
        print(f"    · {row['feature']:<20s} {row['mean_abs_shap']:.4f}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    args = p.parse_args()
    raise SystemExit(main(Path(args.config)))
