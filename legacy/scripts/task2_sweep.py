"""Task 2 — feature-set + hyperparameter sweep across 6 configurations.

Reports CV R² (5-fold spatial blocks at 5°), Asia→US transfer R², top-5
SHAP, and bias for each. Writes data/outputs/sweep_results.json.

Configs:
  A baseline               depth=3, n_est=250, reg_lambda=2.0
  B heavier_reg            depth=3, n_est=250, reg_lambda=8.0, reg_alpha=2.0
  C shallow_more           depth=2, n_est=400, reg_lambda=4.0
  D drop_overfit           baseline params, drop {clay, sand, silt,
                                                   clay_sand_ratio}
  E climate_plus_transferring_soil
                           {bio01, bio04, bio05, bio06, bio12, bio14,
                            bio15, bio17, phh2o, ph_optimality, bdod,
                            cec, aridity_demartonne}
  F climate_only           {bio01, bio04, bio05, bio06, bio12, bio14,
                            bio15, bio17}
"""
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.train import spatial_kfold_split  # noqa: E402

OUT = ROOT / "data" / "outputs" / "sweep_results.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

train = pd.read_parquet(ROOT / "data" / "processed" / "training_features.parquet")
us = pd.read_parquet(ROOT / "data" / "processed" / "us_validation_features.parquet")
target = "log_rs_annual"
drop = {target, "rs_annual", "longitude", "latitude", "site_id", "source", "region"}
ALL_FEATS = [c for c in train.columns if c not in drop]
print(f"All features ({len(ALL_FEATS)}): {ALL_FEATS}")

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
CPTS = (CLIMATE_8 + ["phh2o", "ph_optimality", "bdod", "cec", "aridity_demartonne"])
DROP_OVERFIT = [f for f in ALL_FEATS if f not in {"clay", "sand", "silt", "clay_sand_ratio"}]

CONFIGS = [
    ("A_baseline", "depth=3 n_est=250 reg_lambda=2.0",
     ALL_FEATS, dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                     subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                     reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)),
    ("B_heavier_reg", "depth=3 n_est=250 reg_lambda=8.0 reg_alpha=2.0",
     ALL_FEATS, dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                     subsample=0.70, colsample_bytree=0.85, min_child_weight=8,
                     reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)),
    ("C_shallow_more", "depth=2 n_est=400 reg_lambda=4.0",
     ALL_FEATS, dict(n_estimators=400, max_depth=2, learning_rate=0.04,
                     subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                     reg_alpha=0.1, reg_lambda=4.0, n_jobs=1, verbosity=0)),
    ("D_drop_overfit", "baseline params; drop {clay,sand,silt,clay_sand_ratio}",
     DROP_OVERFIT, dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                        subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                        reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)),
    ("E_climate_plus_transferring_soil", "8 bioclim + phh2o + ph_optimality + bdod + cec + aridity",
     CPTS, dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)),
    ("F_climate_only", "8 bioclim only",
     CLIMATE_8, dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                     subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                     reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)),
]


def run_config(name, desc, feats, params) -> Dict:
    feats = [f for f in feats if f in train.columns]
    tr = train.dropna(subset=[target] + feats).reset_index(drop=True)
    te = us.dropna(subset=[target] + feats).reset_index(drop=True)

    X = tr[feats].to_numpy("float32")
    y = tr[target].to_numpy("float32")

    cv_r2, cv_rmse = [], []
    for k, a, b in spatial_kfold_split(tr, n_splits=5, block_size_deg=5.0, seed=42):
        m = xgb.XGBRegressor(**params)
        m.fit(X[a], y[a])
        p = m.predict(X[b])
        cv_r2.append(r2_score(y[b], p))
        cv_rmse.append(float(np.sqrt(mean_squared_error(y[b], p))))

    final = xgb.XGBRegressor(**params)
    final.fit(X, y)
    Xu = te[feats].to_numpy("float32")
    yu = te[target].to_numpy("float32")
    pu = final.predict(Xu)

    # SHAP — top 5
    try:
        import shap
        explainer = shap.TreeExplainer(final)
        sv = explainer.shap_values(tr[feats].sample(min(800, len(tr)), random_state=42))
        importance = np.abs(sv).mean(axis=0)
        order = np.argsort(importance)[::-1]
        shap_top = [(feats[i], float(importance[i])) for i in order[:5]]
    except Exception as e:
        shap_top = [("shap_failed", 0.0)]
        print(f"  shap error: {e}")

    return {
        "name": name,
        "desc": desc,
        "n_features": len(feats),
        "features": feats,
        "params": {k: v for k, v in params.items() if k != "n_jobs"},
        "n_train": int(len(tr)),
        "n_us": int(len(te)),
        "cv_r2_mean": float(np.mean(cv_r2)),
        "cv_r2_per_fold": [float(x) for x in cv_r2],
        "cv_rmse_mean": float(np.mean(cv_rmse)),
        "transfer_r2": float(r2_score(yu, pu)),
        "transfer_rmse": float(np.sqrt(mean_squared_error(yu, pu))),
        "transfer_mae": float(mean_absolute_error(yu, pu)),
        "transfer_bias": float(np.mean(pu - yu)),
        "transfer_pred_std": float(np.std(pu)),
        "transfer_obs_std": float(np.std(yu)),
        "shap_top5": shap_top,
    }


results = []
for name, desc, feats, params in CONFIGS:
    print(f"\n=== {name} ===  {desc}  (features={len(feats)})")
    r = run_config(name, desc, feats, params)
    results.append(r)
    print(f"  CV R² = {r['cv_r2_mean']:+.3f}    Transfer R² = {r['transfer_r2']:+.3f}    "
          f"bias = {r['transfer_bias']:+.3f}    pred σ = {r['transfer_pred_std']:.3f}")
    print(f"  SHAP top 5: " + ", ".join(f"{f}={v:.3f}" for f, v in r["shap_top5"]))

OUT.write_text(json.dumps({
    "asia_n": int((train.region == "asia").sum()) if "region" in train else len(train),
    "us_n": int((us.region == "us").sum()) if "region" in us else len(us),
    "results": results,
}, indent=2))
print(f"\n→ wrote {OUT}")

# Print summary table
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"{'config':<32s} {'feats':>5s} {'CV R²':>8s} {'Trans R²':>10s} {'bias':>8s} {'pred σ':>8s}")
for r in results:
    print(f"{r['name']:<32s} {r['n_features']:>5d} {r['cv_r2_mean']:>+8.3f} "
          f"{r['transfer_r2']:>+10.3f} {r['transfer_bias']:>+8.3f} "
          f"{r['transfer_pred_std']:>8.3f}")
