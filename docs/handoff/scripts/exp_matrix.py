"""Exploratory E6 (run only after the locked Europe test): train-on-one-continent / test-on-another matrix,
leave-one-continent-out (LOCO), and within-continent spatial-block CV benchmarks. Metric: skill = 1 - RMSE/RMSE_null
(null = training-mean prediction) in log space, plus R2 and n. XGB (locked params) on C8.
"""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score

FEAT, OUT = sys.argv[1:3]
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
         reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0, random_state=0)
d = pd.read_parquet(FEAT).dropna(subset=C8 + ["log_rs"]).reset_index(drop=True)
d["lnP"] = np.log(d.bio12)
from sklearn.linear_model import LinearRegression
LEARNER = sys.argv[3] if len(sys.argv) > 3 else "XGB"
FE = ["bio01", "lnP"] if LEARNER == "OLS-TP" else C8
class M:
    def __init__(self): self.m = LinearRegression() if LEARNER == "OLS-TP" else xgb.XGBRegressor(**P)
    def fit(self, X, y): self.m.fit(X[FE], y); return self
    def predict(self, X): return self.m.predict(X[FE])
CONT = ["Asia", "Europe", "North America", "South America", "Africa", "Oceania"]


def sc(ytr_mean, y, p):
    rm = np.sqrt(np.mean((p - y) ** 2)); r0 = np.sqrt(np.mean((ytr_mean - y) ** 2))
    return dict(n=int(len(y)), r2=round(float(r2_score(y, p)), 3), rmse=round(float(rm), 3), skill=round(float(1 - rm / r0), 3))


def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, min(k, len(u))):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]


R = {"pairwise": {}, "loco": {}, "within_cv": {}}
for tr in CONT:
    a = d[d.continent == tr]
    if len(a) < 30: continue
    m = M().fit(a, a.log_rs)
    for te in CONT:
        if te == tr: continue
        u = d[d.continent == te]
        if len(u) < 15: continue
        R["pairwise"][f"{tr} -> {te}"] = sc(a.log_rs.mean(), u.log_rs.values, m.predict(u))
for te in CONT:
    a, u = d[d.continent != te], d[d.continent == te]
    if len(u) < 15: continue
    R["loco"][te] = sc(a.log_rs.mean(), u.log_rs.values, M().fit(a, a.log_rs).predict(u))
    if len(u) >= 60:
        u = u.reset_index(drop=True); p = np.empty(len(u)); base = np.empty(len(u))
        for tri, vai in folds(u):
            p[vai] = M().fit(u.iloc[tri], u.log_rs.iloc[tri]).predict(u.iloc[vai])
            base[vai] = u.log_rs.iloc[tri].mean()
        rm = np.sqrt(np.mean((p - u.log_rs) ** 2)); r0 = np.sqrt(np.mean((base - u.log_rs) ** 2))
        R["within_cv"][te] = dict(n=len(u), r2=round(float(r2_score(u.log_rs, p)), 3), rmse=round(float(rm), 3), skill=round(float(1 - rm / r0), 3))
json.dump(R, open(OUT, "w"), indent=1)
for k in R:
    print("==", k)
    for kk, v in R[k].items(): print(f"  {kk:35s} {v}")
