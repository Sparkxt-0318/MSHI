"""Task 2 — bootstrap 95% CIs on Asia → US transfer R² for configs F and B.

Both models are retrained on the full Asia training set (no Task-1
relaxation; same 615-Asia table as Run A). Predictions are made once on
the US validation set, then bootstrap-resampled with replacement
(n_bootstrap = 2000, seed=42) to get the sampling distribution of R².

The critical interpretive question: does config F's CI exclude zero?
We report median, 2.5th and 97.5th percentiles, and the answer.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT  = ROOT / "data" / "outputs"

train = pd.read_parquet(PROC / "training_features.parquet")
us    = pd.read_parquet(PROC / "us_validation_features.parquet")
target = "log_rs_annual"

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
ALL_FEATS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec",
             *CLIMATE_8, "c_n_ratio", "clay_sand_ratio", "ph_optimality",
             "aridity_demartonne"]

PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
PARAMS_B = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=8,
                reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)


def fit_predict(feats, params):
    tr = train.dropna(subset=[target] + feats).reset_index(drop=True)
    te = us.dropna(subset=[target] + feats).reset_index(drop=True)
    m = xgb.XGBRegressor(**params)
    m.fit(tr[feats].to_numpy("float32"), tr[target].to_numpy("float32"))
    pred = m.predict(te[feats].to_numpy("float32"))
    obs = te[target].to_numpy("float32")
    return obs, pred, len(tr), len(te)


def bootstrap_r2(obs, pred, n_boot=2000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(obs)
    r2s = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r2s[i] = r2_score(obs[idx], pred[idx])
    return r2s


results = {}
for name, feats, params in [
    ("F_climate_only", CLIMATE_8, PARAMS_F),
    ("B_full_features", ALL_FEATS, PARAMS_B),
]:
    obs, pred, n_train, n_us = fit_predict(feats, params)
    point_r2 = float(r2_score(obs, pred))
    boot = bootstrap_r2(obs, pred, n_boot=2000, seed=42)
    median = float(np.median(boot))
    lo = float(np.quantile(boot, 0.025))
    hi = float(np.quantile(boot, 0.975))
    excludes_zero = (lo > 0) or (hi < 0)
    results[name] = {
        "point_r2": round(point_r2, 4),
        "median": round(median, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "ci_excludes_zero": bool(excludes_zero),
        "n_train": int(n_train),
        "n_us": int(n_us),
        "n_bootstrap": 2000,
    }
    print(f"{name}:")
    print(f"  point R² = {point_r2:+.4f}")
    print(f"  bootstrap median = {median:+.4f}   95% CI = ({lo:+.4f}, {hi:+.4f})")
    print(f"  excludes zero? {excludes_zero}")
    print()

(OUT / "bootstrap_ci.json").write_text(json.dumps(results, indent=2))
print(f"→ wrote {OUT / 'bootstrap_ci.json'}")
