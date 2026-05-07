"""Item 1 Checkpoint 3 — train Full+MODIS configuration.

25 features (varies by landcover encoding):
  8 SoilGrids   : soc, nitrogen, phh2o, clay, sand, silt, bdod, cec
  8 WorldClim   : bio01, bio04, bio05, bio06, bio12, bio14, bio15, bio17
  4 engineered  : c_n_ratio, clay_sand_ratio, ph_optimality, aridity_demartonne
  4 MODIS cont. : npp, lst_day, lst_night, lst_diurnal_range
  + landcover one-hot for IGBP classes with ≥10 training sites

Hyperparameters match Run A's B (best 20-feature config):
    depth=3, n_estimators=250, reg_lambda=8.0, reg_alpha=2.0,
    learning_rate=0.05, subsample=0.85, colsample_bytree=0.85.

Validation:
    1. Asia 5-fold spatial-block CV at 5° blocks, seed=42
    2. Asia → US transfer R² with 2,000-iter bootstrap CI

Outputs:
    data/outputs/Full_MODIS_model.json
    data/outputs/Full_MODIS_metrics.json
    data/outputs/Full_MODIS_shap.json
    data/outputs/Full_MODIS_shap.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.train import spatial_kfold_split  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "outputs"

TARGET = "log_rs_annual"
SOIL = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
BIOCLIM = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
ENG = ["c_n_ratio", "clay_sand_ratio", "ph_optimality", "aridity_demartonne"]
MODIS_CONT = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
PARAMS = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
              subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
              reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)
N_BOOT = 2000
LC_MIN_SITES = 10  # one-hot only IGBP classes with ≥ this many Asia sites


def bootstrap_r2(obs, pred, n_boot, seed=42):
    rng = np.random.default_rng(seed)
    n = len(obs)
    r2s = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r2s[i] = r2_score(obs[idx], pred[idx])
    return r2s


def main() -> int:
    asia = pd.read_parquet(PROC / "training_features_v2.parquet")
    us   = pd.read_parquet(PROC / "us_validation_features_v2.parquet")
    print(f"loaded asia={asia.shape}, us={us.shape}")

    # Determine which IGBP classes have ≥ LC_MIN_SITES in Asia
    asia_lc = asia["landcover"].dropna().astype("Int64")
    lc_counts = asia_lc.value_counts()
    keep_classes = sorted(int(c) for c in lc_counts[lc_counts >= LC_MIN_SITES].index)
    print(f"IGBP classes with ≥{LC_MIN_SITES} Asia sites: {keep_classes}")

    # Build one-hot columns
    def add_lc_onehot(df):
        out = df.copy()
        for c in keep_classes:
            out[f"lc_{c:02d}"] = (out["landcover"].astype("Int64") == c).astype("float32")
        return out

    asia = add_lc_onehot(asia)
    us = add_lc_onehot(us)

    LC_FEATS = [f"lc_{c:02d}" for c in keep_classes]
    FEATS = SOIL + BIOCLIM + ENG + MODIS_CONT + LC_FEATS
    print(f"feature list ({len(FEATS)}): {FEATS}")

    a = asia.dropna(subset=[TARGET] + FEATS).reset_index(drop=True)
    u = us.dropna(subset=[TARGET] + FEATS).reset_index(drop=True)
    print(f"after NaN drop: asia n={len(a)}, us n={len(u)}")

    X = a[FEATS].to_numpy("float32"); y = a[TARGET].to_numpy("float32")

    cv_r2, cv_rmse, cv_mae = [], [], []
    for k, tr, va in spatial_kfold_split(a, n_splits=5, block_size_deg=5.0, seed=42):
        m = xgb.XGBRegressor(**PARAMS)
        m.fit(X[tr], y[tr])
        p = m.predict(X[va])
        cv_r2.append(float(r2_score(y[va], p)))
        cv_rmse.append(float(np.sqrt(mean_squared_error(y[va], p))))
        cv_mae.append(float(mean_absolute_error(y[va], p)))
        print(f"  fold {k}: R²={cv_r2[-1]:+.3f}  RMSE={cv_rmse[-1]:.3f}  n_val={len(va)}")
    cv_mean = float(np.mean(cv_r2))
    print(f"CV mean R² = {cv_mean:+.3f}")

    final = xgb.XGBRegressor(**PARAMS)
    final.fit(X, y)
    Xu = u[FEATS].to_numpy("float32"); yu = u[TARGET].to_numpy("float32")
    pu = final.predict(Xu)
    transfer_r2 = float(r2_score(yu, pu))
    transfer_rmse = float(np.sqrt(mean_squared_error(yu, pu)))
    transfer_mae = float(mean_absolute_error(yu, pu))
    sp, _ = spearmanr(pu, yu)
    boot = bootstrap_r2(yu, pu, n_boot=N_BOOT, seed=42)
    ci_low = float(np.quantile(boot, 0.025))
    ci_high = float(np.quantile(boot, 0.975))
    print(f"Asia → US transfer R² = {transfer_r2:+.4f}  CI ({ci_low:+.4f}, {ci_high:+.4f})")

    final.save_model(str(OUT / "Full_MODIS_model.json"))

    # SHAP
    explainer = shap.TreeExplainer(final)
    Xs = a[FEATS].sample(min(800, len(a)), random_state=42)
    sv = explainer.shap_values(Xs)
    importance = np.abs(sv).mean(axis=0)
    order = np.argsort(importance)[::-1]
    shap_ranking = [{"rank": i + 1, "feature": FEATS[order[i]],
                     "mean_abs_shap": float(importance[order[i]])}
                    for i in range(len(FEATS))]

    plt.figure(figsize=(10, 7))
    shap.summary_plot(sv, Xs, show=False, max_display=20)
    plt.title("Full+MODIS — SHAP summary (Asia training, n=%d)" % len(Xs), fontsize=10)
    plt.tight_layout()
    plt.savefig(OUT / "Full_MODIS_shap.png", dpi=160, bbox_inches="tight")
    plt.close()

    metrics = {
        "config_name": "Full_MODIS",
        "n_features": len(FEATS),
        "features": FEATS,
        "landcover_onehot_classes": keep_classes,
        "n_train": int(len(a)),
        "n_us": int(len(u)),
        "params": {k: v for k, v in PARAMS.items() if k != "n_jobs"},
        "cv": {
            "n_splits": 5,
            "block_size_deg": 5.0,
            "seed": 42,
            "per_fold_r2": cv_r2,
            "mean_r2": cv_mean,
            "std_r2": float(np.std(cv_r2)),
            "mean_rmse": float(np.mean(cv_rmse)),
            "mean_mae": float(np.mean(cv_mae)),
        },
        "transfer": {
            "r2": transfer_r2,
            "rmse_log": transfer_rmse,
            "mae_log": transfer_mae,
            "spearman": float(sp),
            "bias": float(np.mean(pu - yu)),
            "pred_std": float(np.std(pu)),
            "obs_std": float(np.std(yu)),
            "bootstrap_n": N_BOOT,
            "bootstrap_median": float(np.median(boot)),
            "ci_low": ci_low,
            "ci_high": ci_high,
            "ci_excludes_zero": bool(ci_low > 0 or ci_high < 0),
        },
    }
    (OUT / "Full_MODIS_metrics.json").write_text(json.dumps(metrics, indent=2))
    (OUT / "Full_MODIS_shap.json").write_text(json.dumps({
        "config_name": "Full_MODIS",
        "ranking": shap_ranking,
    }, indent=2))

    # Compare to B (Run A)
    runA_B = json.load(open(OUT / "bootstrap_ci.json"))["B_full_features"]
    sweep = json.load(open(OUT / "sweep_results.json"))
    runA_B_cv = next(c for c in sweep["results"] if c["name"] == "B_heavier_reg")["cv_r2_mean"]
    print(f"\nRun A B CV R² = {runA_B_cv:+.3f}, transfer R² = {runA_B['point_r2']:+.3f}")
    print(f"Full+MODIS CV R² = {cv_mean:+.3f}, transfer R² = {transfer_r2:+.3f}")
    print(f"Δ CV = {cv_mean - runA_B_cv:+.3f}, Δ transfer = {transfer_r2 - runA_B['point_r2']:+.3f}")
    print(f"\nTop 10 SHAP for Full+MODIS:")
    for r in shap_ranking[:10]:
        print(f"  {r['rank']:>2d}. {r['feature']:<22s}  {r['mean_abs_shap']:.4f}")
    modis_ranks = [r["rank"] for r in shap_ranking
                   if r["feature"] in MODIS_CONT or r["feature"].startswith("lc_")]
    print(f"\nMODIS feature ranks: {modis_ranks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
