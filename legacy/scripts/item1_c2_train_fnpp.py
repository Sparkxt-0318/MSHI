"""Item 1 Checkpoint 2 — train F+NPP (climate + MODIS continuous), 12 features.

Configuration matches Run A's F config hyperparameters:
    depth=3, n_estimators=250, reg_lambda=2.0, reg_alpha=0.5,
    learning_rate=0.05, subsample=0.85, colsample_bytree=0.85.

Validation:
    1. Asia 5-fold spatial-block CV at 5° blocks, seed=42 (matches Run A)
    2. Asia → US transfer R² with 2,000-iter bootstrap CI on US set

Outputs:
    data/outputs/F_NPP_model.json
    data/outputs/F_NPP_metrics.json
    data/outputs/F_NPP_shap.json
    data/outputs/F_NPP_shap.png
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
FEATS = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17",
         "npp", "lst_day", "lst_night", "lst_diurnal_range"]
PARAMS = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
              subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
              reg_alpha=0.5, reg_lambda=2.0, n_jobs=1, verbosity=0)
N_BOOT = 2000


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

    a = asia.dropna(subset=[TARGET] + FEATS).reset_index(drop=True)
    u = us.dropna(subset=[TARGET] + FEATS).reset_index(drop=True)
    print(f"after NaN drop: asia n={len(a)}, us n={len(u)}")

    X = a[FEATS].to_numpy("float32"); y = a[TARGET].to_numpy("float32")

    # Spatial-block CV
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
    print(f"CV mean R² = {cv_mean:+.3f} (per-fold std {np.std(cv_r2):.3f})")

    # Final fit on all of Asia, predict on US
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

    final.save_model(str(OUT / "F_NPP_model.json"))

    # SHAP
    explainer = shap.TreeExplainer(final)
    Xs = a[FEATS].sample(min(800, len(a)), random_state=42)
    sv = explainer.shap_values(Xs)
    importance = np.abs(sv).mean(axis=0)
    order = np.argsort(importance)[::-1]
    shap_ranking = [{"rank": i + 1, "feature": FEATS[order[i]],
                     "mean_abs_shap": float(importance[order[i]])}
                    for i in range(len(FEATS))]

    plt.figure(figsize=(9, 6))
    shap.summary_plot(sv, Xs, show=False, max_display=12)
    plt.title("F+NPP — SHAP summary (Asia training, n=%d)" % len(Xs), fontsize=10)
    plt.tight_layout()
    plt.savefig(OUT / "F_NPP_shap.png", dpi=160, bbox_inches="tight")
    plt.close()

    metrics = {
        "config_name": "F_NPP",
        "n_features": len(FEATS),
        "features": FEATS,
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
    (OUT / "F_NPP_metrics.json").write_text(json.dumps(metrics, indent=2))
    (OUT / "F_NPP_shap.json").write_text(json.dumps({
        "config_name": "F_NPP",
        "ranking": shap_ranking,
    }, indent=2))

    # Compare to F (Run A)
    runA_F = json.load(open(OUT / "bootstrap_ci.json"))["F_climate_only"]
    sweep = json.load(open(OUT / "sweep_results.json"))
    runA_F_cv = next(c for c in sweep["results"] if c["name"] == "F_climate_only")["cv_r2_mean"]
    print(f"\nRun A F CV R² = {runA_F_cv:+.3f}, transfer R² = {runA_F['point_r2']:+.3f}")
    print(f"F+NPP CV R² = {cv_mean:+.3f}, transfer R² = {transfer_r2:+.3f}")
    print(f"Δ CV = {cv_mean - runA_F_cv:+.3f}, Δ transfer = {transfer_r2 - runA_F['point_r2']:+.3f}")
    print(f"\nTop 5 SHAP for F+NPP:")
    for r in shap_ranking[:5]:
        print(f"  {r['rank']}. {r['feature']:<20s}  {r['mean_abs_shap']:.4f}")
    npp_rank = next((r["rank"] for r in shap_ranking if r["feature"] == "npp"), None)
    print(f"\nNPP rank in F+NPP: {npp_rank}/{len(FEATS)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
