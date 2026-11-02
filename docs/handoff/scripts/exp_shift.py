"""Exploratory E2/E3 on Asia -> North America (NA already used in earlier work; exploratory only).
E2: data hygiene — QC vs repo filters (site-mean targets) on NA transfer R2.
E3: covariate vs concept shift — adversarial AUC; importance-weighted training; Asia-trained vs NA-trained (spatial CV)
    on the same NA sites; pooled OLS with continent interactions (which slopes differ between continents).
"""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb, statsmodels.formula.api as smf
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.linear_model import LogisticRegression

V3, OUT = sys.argv[1], sys.argv[2]
T = "log_rs"; C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
SOIL = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
         reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0, random_state=0)
rng = np.random.default_rng(42)


def ci(y, p, n=2000):
    b = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    return [round(float(np.quantile(b, .025)), 3), round(float(np.quantile(b, .975)), 3)]


def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]


R = {}
for tag in ["repo", "qc"]:
    d = pd.read_parquet(f"{V3}/features_v3_{tag}.parquet")
    for name, f in [("C8", C8), ("C8+NPP", C8 + ["npp"]), ("C8+SOIL", C8 + SOIL)]:
        a = d[d.continent == "Asia"].dropna(subset=[T] + f); u = d[d.continent == "North America"].dropna(subset=[T] + f)
        p = xgb.XGBRegressor(**P).fit(a[f], a[T]).predict(u[f])
        R[f"E2_{tag}_{name}"] = dict(n_train=len(a), n_test=len(u), r2=round(float(r2_score(u[T], p)), 3), ci=ci(u[T].values, p))

d = pd.read_parquet(f"{V3}/features_v3_qc.parquet")
f = C8 + ["npp"]
a = d[d.continent == "Asia"].dropna(subset=[T] + f).reset_index(drop=True)
u = d[d.continent == "North America"].dropna(subset=[T] + f).reset_index(drop=True)
# adversarial validation
Xall = pd.concat([a[f], u[f]]); lab = np.r_[np.zeros(len(a)), np.ones(len(u))]
clf = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, n_jobs=2, verbosity=0)
pr = cross_val_predict(clf, Xall, lab, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")[:, 1]
R["E3_adversarial_auc_asia_vs_na"] = round(float(roc_auc_score(lab, pr)), 3)
clf.fit(Xall, lab); imp = pd.Series(clf.feature_importances_, f).sort_values(ascending=False)
R["E3_adversarial_top_features"] = imp.head(4).round(3).to_dict()
# importance weighting w = p/(1-p) for Asia rows (density ratio NA/Asia), clipped
pa = pr[:len(a)].clip(0.01, 0.99); w = (pa / (1 - pa)); w = np.clip(w / w.mean(), 0, 20)
p0 = xgb.XGBRegressor(**P).fit(a[f], a[T]).predict(u[f])
p1 = xgb.XGBRegressor(**P).fit(a[f], a[T], sample_weight=w).predict(u[f])
R["E3_unweighted_r2"] = round(float(r2_score(u[T], p0)), 3)
R["E3_importance_weighted_r2"] = round(float(r2_score(u[T], p1)), 3)
R["E3_effective_sample_size_weighted"] = round(float(w.sum() ** 2 / (w ** 2).sum()), 1)
# NA-trained benchmark (spatial-block CV within NA) on the same NA sites
pn = np.empty(len(u))
for tr, va in folds(u):
    pn[va] = xgb.XGBRegressor(**P).fit(u[f].iloc[tr], u[T].iloc[tr]).predict(u[f].iloc[va])
R["E3_NA_within_spatialCV_r2"] = round(float(r2_score(u[T], pn)), 3)
R["E3_asia_trained_r2_same_sites"] = R["E3_unweighted_r2"]
# Pooled interaction model: which slopes differ between Asia and NA?
pool = pd.concat([a.assign(cont="Asia"), u.assign(cont="NA")]).dropna(subset=["clay"])
pool["lnP"] = np.log(pool.bio12); pool["lnNPP"] = np.log(pool.npp.clip(lower=10))
for v in ["bio01", "lnP", "bio15", "clay", "lnNPP"]:
    pool[v + "_z"] = (pool[v] - pool[v].mean()) / pool[v].std()
fit = smf.ols("log_rs ~ (bio01_z + lnP_z + bio15_z + clay_z + lnNPP_z) * C(cont)", data=pool).fit(cov_type="HC3")
tab = pd.DataFrame({"coef": fit.params, "lo": fit.conf_int()[0], "hi": fit.conf_int()[1], "p": fit.pvalues}).round(3)
R["E3_pooled_interactions"] = tab.loc[[i for i in tab.index if ":" in i or i.endswith("_z")]].to_dict(orient="index")
R["E3_pooled_n"] = int(len(pool))
json.dump(R, open(OUT, "w"), indent=1, default=str)
for k, v in R.items():
    if k != "E3_pooled_interactions": print(k, v)
print(tab.to_string())
