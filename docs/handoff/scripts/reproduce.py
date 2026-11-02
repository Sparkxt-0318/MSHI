"""Independent reproduction of the three headline Asia->US transfer numbers.

Uses the committed processed tables (training_features_v2 / us_validation_features_v2)
and the exact feature lists and hyperparameters from the repo scripts:
  F          : scripts/task2_bootstrap_ci.py   (PARAMS_F)
  F+NPP      : scripts/item1_c2_train_fnpp.py  (PARAMS)
  Full+MODIS : scripts/item1_c3_train_full_modis.py (PARAMS, IGBP one-hot >=10 Asia sites)
Also: each config re-scored on the common site set, with matched hyperparameters,
with paired bootstrap, and across 20 XGBoost seeds.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from scipy.stats import spearmanr

REPO = Path(sys.argv[1])
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO))
from src.train import spatial_kfold_split  # noqa

T = "log_rs_annual"
SOIL = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
BIO = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
ENG = ["c_n_ratio", "clay_sand_ratio", "ph_optimality", "aridity_demartonne"]
MOD = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
P_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.70, colsample_bytree=0.85,
           min_child_weight=6, reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
P_FNPP = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85,
              min_child_weight=4, reg_alpha=0.5, reg_lambda=2.0, n_jobs=1, verbosity=0)
P_FULL = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85,
              min_child_weight=4, reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)

asia = pd.read_parquet(REPO / "data/processed/training_features_v2.parquet")
us = pd.read_parquet(REPO / "data/processed/us_validation_features_v2.parquet")
lc = asia["landcover"].dropna().astype(int).value_counts()
keep = sorted(int(c) for c in lc[lc >= 10].index)
for df in (asia, us):
    for c in keep:
        df[f"lc_{c}"] = (df["landcover"] == c).astype("float32")
    df.loc[df["landcover"].isna(), [f"lc_{c}" for c in keep]] = np.nan
LC = [f"lc_{c}" for c in keep]
FULL = SOIL + BIO + ENG + MOD + LC

CONFIGS = {"F": (BIO, P_F), "F+NPP": (BIO + MOD, P_FNPP), "Full+MODIS": (FULL, P_FULL)}


def boot(obs, preds: dict, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    out = {k: np.empty(n) for k in preds}
    for i in range(n):
        idx = rng.integers(0, len(obs), len(obs))
        for k, p in preds.items():
            out[k][i] = r2_score(obs[idx], p[idx])
    return out


def fit_pred(a, u, feats, params, seed=0):
    m = xgb.XGBRegressor(**params, random_state=seed)
    m.fit(a[feats].to_numpy("float32"), a[T].to_numpy("float32"))
    return m.predict(u[feats].to_numpy("float32"))


def metrics(yu, pu):
    rs_o, rs_p = np.exp(yu), np.exp(pu)
    return dict(r2=float(r2_score(yu, pu)), rmse_log=float(np.sqrt(mean_squared_error(yu, pu))),
                spearman=float(spearmanr(yu, pu)[0]), bias_log=float(np.mean(pu - yu)),
                rmse_rs=float(np.sqrt(np.mean((rs_p - rs_o) ** 2))), mae_rs=float(np.mean(np.abs(rs_p - rs_o))),
                pred_sd=float(np.std(pu)), obs_sd=float(np.std(yu)))


res = {"versions": {"xgboost": xgb.__version__, "numpy": np.__version__, "pandas": pd.__version__},
       "igbp_classes_onehot": keep, "as_published": {}, "common_set": {}}

# 1) as published: each config drops its own NaNs
for name, (feats, params) in CONFIGS.items():
    a = asia.dropna(subset=[T] + feats).reset_index(drop=True)
    u = us.dropna(subset=[T] + feats).reset_index(drop=True)
    X, y = a[feats].to_numpy("float32"), a[T].to_numpy("float32")
    cv = []
    for k, tr, va in spatial_kfold_split(a, n_splits=5, block_size_deg=5.0, seed=42):
        m = xgb.XGBRegressor(**params); m.fit(X[tr], y[tr]); cv.append(r2_score(y[va], m.predict(X[va])))
    pu = fit_pred(a, u, feats, params)
    yu = u[T].to_numpy("float32")
    b = boot(yu, {"x": pu})["x"]
    seeds = [r2_score(yu, fit_pred(a, u, feats, params, s)) for s in range(20)]
    res["as_published"][name] = dict(n_train=len(a), n_us=len(u), n_feat=len(feats), cv_r2=float(np.mean(cv)),
                                     cv_per_fold=[float(c) for c in cv], **metrics(yu, pu),
                                     ci=[float(np.quantile(b, .025)), float(np.quantile(b, .975))],
                                     seed_r2_min=float(min(seeds)), seed_r2_max=float(max(seeds)),
                                     seed_r2_mean=float(np.mean(seeds)))

# 2) common site set (rows complete for Full+MODIS features)
need = list(dict.fromkeys(FULL))
a = asia.dropna(subset=[T] + need).reset_index(drop=True)
u = us.dropna(subset=[T] + need).reset_index(drop=True)
yu = u[T].to_numpy("float32")
preds = {}
for name, (feats, params) in CONFIGS.items():
    preds[name] = fit_pred(a, u, feats, params)
    preds[name + " [P_FNPP params]"] = fit_pred(a, u, feats, P_FNPP)
preds["intercept-only (Asia mean)"] = np.full(len(u), a[T].mean(), dtype="float32")
b = boot(yu, preds)
cs = {"n_train": len(a), "n_us": len(u)}
for k, p in preds.items():
    cs[k] = dict(**metrics(yu, p), ci=[float(np.quantile(b[k], .025)), float(np.quantile(b[k], .975))])
for x, y_ in [("F+NPP", "F"), ("Full+MODIS", "F+NPP"), ("Full+MODIS", "F")]:
    d = b[x] - b[y_]
    cs[f"paired_diff {x} - {y_}"] = dict(point=float(r2_score(yu, preds[x]) - r2_score(yu, preds[y_])),
                                         ci=[float(np.quantile(d, .025)), float(np.quantile(d, .975))],
                                         p_le0=float(np.mean(d <= 0)))
res["common_set"] = cs
(OUT / "reproduction.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=1))
