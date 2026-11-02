# Verbatim fit_score/ci from exp_ablation.py (lines 16-31), applied to the original committed tables (lines 61-65).
# The bootstrap RNG (default_rng(1)) is advanced through the four earlier ci() calls (n_test 326, 240, 326, 240).
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score
print("xgboost", xgb.__version__)
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
         reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0)
rng = np.random.default_rng(1)
def ci(y, p):
    b = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(1000))]
    return [round(float(np.quantile(b, .025)), 3), round(float(np.quantile(b, .975)), 3)]
def fit_score(a, u, feats=C8, y="y"):
    a, u = a.dropna(subset=feats + [y]), u.dropna(subset=feats + [y])
    r2s = [r2_score(u[y], xgb.XGBRegressor(**P, random_state=s).fit(a[feats], a[y]).predict(u[feats])) for s in range(5)]
    p = xgb.XGBRegressor(**P, random_state=0).fit(a[feats], a[y]).predict(u[feats])
    return dict(n_train=len(a), n_test=len(u), r2=round(float(r2_score(u[y], p)), 3), ci=ci(u[y].values, p),
                r2_seed_mean=round(float(np.mean(r2s)), 3), seeds=[round(float(x), 4) for x in r2s], r2_full=float(r2_score(u[y], p)))
Pp = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed/"
o_a = pd.read_parquet(Pp + "training_features_v2.parquet"); o_u = pd.read_parquet(Pp + "us_validation_features_v2.parquet")
for df in (o_a, o_u): df["y"] = df.log_rs_annual
# advance RNG exactly as the 4 earlier ci() calls would
for n in (326, 240, 326, 240):
    for _ in range(1000): rng.integers(0, n, n)
print("synced:", fit_score(o_a, o_u))
rng = np.random.default_rng(1)
print("unsynced (fresh rng):", fit_score(o_a, o_u))
print("JSON: r2 0.131, ci [0.021, 0.228], seed mean 0.135")
