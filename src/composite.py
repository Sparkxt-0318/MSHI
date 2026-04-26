"""
composite.py — build the climate-corrected MSHI-Geo anomaly score.

Logic:
  1. Train a *climate-only* baseline that predicts log_rs_annual from
     climate features (temp, precip, seasonality) at the same training points.
  2. Apply both the full model and the climate baseline to the prediction grid.
  3. Compute anomaly = exp(log_full) / exp(log_climate)
                     = predicted_Rs / climate_expected_Rs

Values >1 → soil supports MORE microbial activity than climate alone predicts.
Values <1 → soil supports LESS than climate alone predicts (degradation signal).

Run:
    python src/composite.py --config configs/mshi_geo.yaml \\
                            --predictions data/processed/asia_grid_5km_predictions.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("mshi_geo.composite")


def train_climate_baseline(
    train_table: pd.DataFrame, climate_features: List[str],
    target: str, params: dict,
) -> "xgboost.XGBRegressor":
    """Fit a climate-only XGBoost on the same training data."""
    import xgboost as xgb

    feats = [f for f in climate_features if f in train_table.columns]
    if len(feats) < 3:
        raise RuntimeError(f"Too few climate features available: {feats}")

    df = train_table.dropna(subset=[target] + feats)
    LOG.info("Climate baseline: training on %d rows × %d features",
             len(df), len(feats))

    model = xgb.XGBRegressor(**params, verbosity=0)
    model.fit(df[feats].to_numpy("float32"),
              df[target].to_numpy("float32"))
    LOG.info("Climate baseline trained")
    return model, feats


def apply_anomaly(
    pred_df: pd.DataFrame,
    full_log_col: str,
    climate_model,
    climate_features: List[str],
    out_col: str = "mshi_geo_anomaly",
) -> pd.DataFrame:
    """Compute anomaly = exp(log_full) / exp(log_climate) for each cell."""
    out = pred_df.copy()
    feats = [f for f in climate_features if f in out.columns]
    valid = out[feats].notna().all(axis=1).to_numpy()

    log_climate = np.full(len(out), np.nan, dtype="float32")
    if valid.any():
        log_climate[valid] = climate_model.predict(
            out.loc[valid, feats].to_numpy("float32")
        )

    out["log_rs_climate"] = log_climate
    out["rs_climate_pred"] = np.exp(log_climate)
    out[out_col] = np.exp(out[full_log_col]) / np.exp(log_climate)
    return out


def main(cfg_path: Path, predictions_path: Path) -> int:
    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]

    # Load training table to fit climate baseline
    train_path = root / cfg["paths"]["feature_table_train"]
    if not train_path.exists():
        LOG.error("Training table not found: %s", train_path)
        return 1
    train_df = pd.read_parquet(train_path)

    target = cfg["model"]["target"]
    climate_features = cfg["climate_baseline"]["features"]
    cb_params = cfg["climate_baseline"]["xgboost_params"]

    climate_model, used_feats = train_climate_baseline(
        train_df, climate_features, target, cb_params
    )

    # Load predictions and compute anomaly
    pred_df = pd.read_parquet(predictions_path)
    LOG.info("Loaded %d prediction rows", len(pred_df))

    out_col = cfg["composite"]["output_column"]
    out = apply_anomaly(
        pred_df, full_log_col="log_rs_pred",
        climate_model=climate_model,
        climate_features=used_feats,
        out_col=out_col,
    )

    out_path = predictions_path.with_name(
        predictions_path.stem + "_anomaly.parquet"
    )
    out.to_parquet(out_path, index=False)
    LOG.info("Saved anomaly composite → %s", out_path)

    # Summary
    s = out[out_col].describe()
    print("\n=== MSHI-Geo anomaly composite stats ===")
    print(f"  mean    {s['mean']:.3f}")
    print(f"  std     {s['std']:.3f}")
    print(f"  p5      {out[out_col].quantile(0.05):.3f}")
    print(f"  p50     {s['50%']:.3f}")
    print(f"  p95     {out[out_col].quantile(0.95):.3f}")
    print(f"  fraction <0.75 (degraded): {(out[out_col]<0.75).mean()*100:.1f}%")
    print(f"  fraction >1.25 (healthy):  {(out[out_col]>1.25).mean()*100:.1f}%")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    p.add_argument("--predictions", required=True)
    args = p.parse_args()
    raise SystemExit(main(Path(args.config), Path(args.predictions)))
