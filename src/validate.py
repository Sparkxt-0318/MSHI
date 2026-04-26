"""
validate.py — external validation on a US held-out subset.

This is the cross-continental transfer test: we trained on Asia,
predict on US points, and measure how well the model generalizes.
A model that holds up on US data is significantly more publishable
than one that only works inside its training domain.

Reads:
    data/processed/us_validation_features.parquet
    data/outputs/mshi_geo_xgb.json

Writes:
    data/outputs/validation_report.json
    data/outputs/validation_scatter.png
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

LOG = logging.getLogger("mshi_geo.validate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main(cfg_path: Path) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import xgboost as xgb

    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]

    val_path = root / cfg["paths"]["feature_table_us"]
    if not val_path.exists():
        LOG.error("US validation table not found: %s", val_path)
        LOG.error("Run feature extraction on US points first.")
        return 1

    df = pd.read_parquet(val_path)
    LOG.info("Loaded US validation: %d rows × %d cols", len(df), df.shape[1])

    target = cfg["model"]["target"]
    model = xgb.XGBRegressor()
    model.load_model(str(root / cfg["paths"]["model"]))

    metrics_path = root / "data" / "outputs" / "training_metrics.json"
    train_meta = json.loads(metrics_path.read_text())
    feature_cols: List[str] = train_meta["feature_cols"]

    df_clean = df.dropna(subset=[target] + feature_cols)
    LOG.info("After NaN drop: %d rows", len(df_clean))

    X = df_clean[feature_cols].to_numpy(dtype="float32")
    y = df_clean[target].to_numpy(dtype="float32")
    pred = model.predict(X)

    report = {
        "n_us_points": int(len(df_clean)),
        "asia_to_us_transfer": {
            "r2":   float(r2_score(y, pred)),
            "rmse": float(np.sqrt(mean_squared_error(y, pred))),
            "mae":  float(mean_absolute_error(y, pred)),
            "bias": float(np.mean(pred - y)),
        },
    }

    # Asia CV reference for context
    if train_meta.get("cv_mean_r2") is not None:
        report["asia_cv_reference"] = {
            "r2":   train_meta["cv_mean_r2"],
            "rmse": train_meta["cv_mean_rmse"],
        }
        gap = report["asia_cv_reference"]["r2"] - report["asia_to_us_transfer"]["r2"]
        report["transfer_gap_r2"] = float(gap)

    out_json = root / cfg["paths"]["validation_report"]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2))
    LOG.info("Saved validation report → %s", out_json)

    # Scatter plot
    plt.figure(figsize=(7, 7))
    plt.scatter(y, pred, s=14, alpha=0.45, edgecolor="none")
    lo, hi = float(min(y.min(), pred.min())), float(max(y.max(), pred.max()))
    plt.plot([lo, hi], [lo, hi], "k--", lw=1.0, alpha=0.6)
    plt.xlabel(f"observed {target}")
    plt.ylabel(f"predicted {target}")
    plt.title(
        f"Asia → US transfer\nR²={report['asia_to_us_transfer']['r2']:.3f}  "
        f"RMSE={report['asia_to_us_transfer']['rmse']:.3f}  "
        f"n={report['n_us_points']}"
    )
    plt.tight_layout()
    out_png = root / "data" / "outputs" / "validation_scatter.png"
    plt.savefig(out_png, dpi=160)
    plt.close()
    LOG.info("Saved scatter → %s", out_png)

    print("\n=== VALIDATION SUMMARY (Asia → US) ===")
    for k, v in report["asia_to_us_transfer"].items():
        print(f"  {k:<6s} {v:.4f}")
    if "transfer_gap_r2" in report:
        print(f"  R² gap vs. Asia CV: {report['transfer_gap_r2']:.3f}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    args = p.parse_args()
    raise SystemExit(main(Path(args.config)))
