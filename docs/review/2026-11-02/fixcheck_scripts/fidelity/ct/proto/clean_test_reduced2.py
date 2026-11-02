"""Locked clean test (v3/ANALYSIS_PLAN_LOCKED.md). Asia-only selection, single scoring on Europe.
Usage: python clean_test.py FEATURES_PARQUET OUT_JSON [--test-continent Europe] [--no-score]
"""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.inspection import permutation_importance

FEAT, OUT = sys.argv[1], sys.argv[2]
TEST = sys.argv[sys.argv.index("--test-continent") + 1] if "--test-continent" in sys.argv else "Europe"
TRAIN = sys.argv[sys.argv.index("--train-continent") + 1] if "--train-continent" in sys.argv else "Asia"
NO_SCORE = "--no-score" in sys.argv
T = "log_rs"
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
SOIL = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
MOD = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
SETS = {"C8": C8, "C8+NPP": C8 + ["npp"], "C8+MODIS": C8 + MOD, "C8+SOIL": C8 + SOIL, "ALL": C8 + SOIL + MOD}
XGBP = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85,
            min_child_weight=4, reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0)


def make(learner, seed=0):
    if learner == "XGB": return xgb.XGBRegressor(**XGBP, random_state=seed)
    if learner == "RF": return RandomForestRegressor(40, min_samples_leaf=5, max_features=0.5, random_state=seed, n_jobs=2)
    return LinearRegression()


def design(df, learner, feats):
    if learner == "OLS-TP":
        return np.c_[df.bio01.values, np.log(df.bio12.values)]
    return df[feats].to_numpy("float32")


def folds(df, seed, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); rng = np.random.default_rng(seed); rng.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]


d = pd.read_parquet(FEAT)
asia_all, eu_all = d[d.continent == TRAIN], d[d.continent == TEST]
cands = [(s, l) for s in SETS for l in ["XGB", "RF"]] + [("TP", "OLS-TP")]
sel = []
for s, l in cands:
    feats = ["bio01", "bio12"] if l == "OLS-TP" else SETS[s]
    a = asia_all.dropna(subset=[T] + feats).reset_index(drop=True)
    X, y = design(a, l, feats), a[T].values
    r2 = []
    for seed in (42, 43, 44):
        for tr, va in folds(a, seed):
            m = make(l).fit(X[tr], y[tr]); r2.append(r2_score(y[va], m.predict(X[va])))
    sel.append(dict(set=s, learner=l, n_pred=len(feats) if l != "OLS-TP" else 2, n_train=len(a), cv_r2=float(np.mean(r2)),
                    cv_r2_sd=float(np.std(r2))))
sel = sorted(sel, key=lambda r: -r["cv_r2"])
best = sel[0]
for r in sel[1:]:
    if best["cv_r2"] - r["cv_r2"] <= 0.01 and r["n_pred"] < best["n_pred"]: best = r
R = {"plan_sha256": open(FEAT.rsplit("/", 1)[0] + "/ANALYSIS_PLAN_LOCKED.sha256").read().split()[0],
     "train": TRAIN, "test": TEST, "selection_table": sel, "selected": best}
print(json.dumps({"selected": best}, indent=1)); print(pd.DataFrame(sel).to_string())
if NO_SCORE:
    json.dump(R, open(OUT, "w"), indent=1); sys.exit()


def boot_ci(y, p, lon=None, lat=None, deg=None, n=300, seed=42):
    rng = np.random.default_rng(seed)
    if deg is None:
        bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    else:
        b = (np.floor(lon / deg).astype(int).astype(str) + "_" + np.floor(lat / deg).astype(int).astype(str))
        u = np.unique(b); idx = {k: np.where(b == k)[0] for k in u}; bs = []
        for _ in range(n):
            i = np.concatenate([idx[k] for k in rng.choice(u, len(u))]); bs.append(r2_score(y[i], p[i]))
    return [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]


def score(s, l, seed=0):
    feats = ["bio01", "bio12"] if l == "OLS-TP" else SETS[s]
    a = asia_all.dropna(subset=[T] + feats).reset_index(drop=True)
    e = eu_all.dropna(subset=[T] + feats).reset_index(drop=True)
    m = make(l, seed).fit(design(a, l, feats), a[T].values)
    return a, e, feats, m, m.predict(design(e, l, feats))


def metrics(y, p, lon, lat, ybase):
    ro, rp = np.exp(y), np.exp(p)
    return dict(n=int(len(y)), r2=float(r2_score(y, p)), ci_site=boot_ci(y, p), ci_block2=boot_ci(y, p, lon, lat, 2.0),
                rmse_rs=float(np.sqrt(np.mean((rp - ro) ** 2))), mae_rs=float(np.mean(np.abs(rp - ro))),
                rmse_rs_intercept=float(np.sqrt(np.mean((np.exp(ybase) - ro) ** 2))),
                bias_log=float(np.mean(p - y)), spearman=float(pd.Series(y).corr(pd.Series(p), method="spearman")))


a, e, feats, m, p = score(best["set"], best["learner"])
y = e[T].values
R["primary"] = metrics(y, p, e.lon.values, e.lat.values, np.full(len(y), a[T].mean()))
R["primary"]["seed_r2_range"] = ([float(r2_score(y, score(best["set"], best["learner"], s)[4])) for s in range(4)]
                                 if best["learner"] != "OLS-TP" else None)
if R["primary"]["seed_r2_range"]: R["primary"]["seed_r2_range"] = [min(R["primary"]["seed_r2_range"]), max(R["primary"]["seed_r2_range"])]

# ---- AOA (Meyer & Pebesma 2021): DI in standardised, importance-weighted predictor space
Xa = design(a, best["learner"], feats).astype(float); Xe = design(e, best["learner"], feats).astype(float)
mu, sd = Xa.mean(0), Xa.std(0); sd[sd == 0] = 1
if best["learner"] == "OLS-TP":
    w = np.ones(Xa.shape[1])
else:
    w = permutation_importance(m, Xa, a[T].values, n_repeats=10, random_state=0).importances_mean.clip(min=0)
    w = w / w.sum() if w.sum() > 0 else np.ones_like(w)
Za, Ze = (Xa - mu) / sd * w, (Xe - mu) / sd * w
from scipy.spatial.distance import cdist
dbar = cdist(Za, Za)[np.triu_indices(len(Za), 1)].mean()
train_di = np.empty(len(Za))
for tr, va in folds(a, 42):
    train_di[va] = cdist(Za[va], Za[tr]).min(1) / dbar
q1, q3 = np.quantile(train_di, [.25, .75]); thr = q3 + 1.5 * (q3 - q1)
thr = train_di[train_di <= thr].max()
di_e = cdist(Ze, Za).min(1) / dbar
inside = di_e <= thr
R["aoa"] = dict(threshold=float(thr), frac_inside=float(inside.mean()), n_inside=int(inside.sum()), n_outside=int((~inside).sum()))
if inside.sum() > 10 and (~inside).sum() > 10:
    R["aoa"]["inside"] = metrics(y[inside], p[inside], e.lon.values[inside], e.lat.values[inside], np.full(inside.sum(), a[T].mean()))
    R["aoa"]["outside"] = metrics(y[~inside], p[~inside], e.lon.values[~inside], e.lat.values[~inside], np.full((~inside).sum(), a[T].mean()))
    rng = np.random.default_rng(7); diffs = []
    ii, oo = np.where(inside)[0], np.where(~inside)[0]
    for _ in range(300):
        bi, bo = rng.choice(ii, len(ii)), rng.choice(oo, len(oo))
        diffs.append(r2_score(y[bi], p[bi]) - r2_score(y[bo], p[bo]))
    R["aoa"]["r2_diff_inside_minus_outside"] = dict(point=float(r2_score(y[inside], p[inside]) - r2_score(y[~inside], p[~inside])),
                                                     ci=[float(np.quantile(diffs, .025)), float(np.quantile(diffs, .975))])
# DI terciles: squared error vs DI
R["aoa"]["sq_err_by_DI_tercile"] = [float(np.mean((y - p)[g] ** 2)) for g in np.array_split(np.argsort(di_e), 3)]

# ---- secondary: every candidate on the test continent
R["all_candidates_on_test"] = []
for s, l in cands:
    a2, e2, f2, m2, p2 = score(s, l)
    R["all_candidates_on_test"].append(dict(set=s, learner=l, n=len(e2), r2=float(r2_score(e2[T], p2)),
                                            ci_site=boot_ci(e2[T].values, p2)))
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps({k: R[k] for k in ["primary", "aoa"]}, indent=1))
print(pd.DataFrame(R["all_candidates_on_test"]).to_string())
