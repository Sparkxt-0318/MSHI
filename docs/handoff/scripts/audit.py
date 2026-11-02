"""Leakage / site-selection / statistics audit for checkpoint 1.
Run with xgboost 2.1.4 (the version that reproduces the published numbers exactly).
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score
from scipy.stats import spearmanr, pearsonr
from scipy.spatial import cKDTree

REPO = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
T = "log_rs_annual"
BIO = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
MOD = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
P_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.70, colsample_bytree=0.85,
           min_child_weight=6, reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
P_FNPP = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85,
              min_child_weight=4, reg_alpha=0.5, reg_lambda=2.0, n_jobs=1, verbosity=0)
asia = pd.read_parquet(REPO / "data/processed/training_features_v2.parquet")
us = pd.read_parquet(REPO / "data/processed/us_validation_features_v2.parquet")
R = {}


def hav_km(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def xyz(df):
    la, lo = np.radians(df.latitude.values), np.radians(df.longitude.values)
    return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)] * 6371


# --- 1. overlap & duplicates
R["n_asia_table"], R["n_us_table"] = len(asia), len(us)
R["site_id_overlap"] = len(set(asia.site_id) & set(us.site_id))
R["exact_coord_dups_asia"] = int(asia.duplicated(["latitude", "longitude"]).sum())
R["exact_coord_dups_us"] = int(us.duplicated(["latitude", "longitude"]).sum())
ta, tu = cKDTree(xyz(asia)), cKDTree(xyz(us))
d_cross, _ = tu.query(xyz(asia))
R["min_train_test_distance_km"] = float(d_cross.min())
for name, df, tr in [("asia", asia, ta), ("us", us, tu)]:
    d, _ = tr.query(xyz(df), k=2); nn = d[:, 1]
    R[f"nn_dist_{name}_km"] = dict(min=float(nn.min()), median=float(np.median(nn)),
                                  n_lt_5km=int((nn < 5).sum()), n_lt_10km=int((nn < 10).sum()),
                                  n_lt_25km=int((nn < 25).sum()))
R["source_counts"] = {"asia": asia.source.value_counts().to_dict(), "us": us.source.value_counts().to_dict()}

# --- 2. rough geography of the 'Asia' bbox (25-180E, -10-80N)
def geo(r):
    lo, la = r.longitude, r.latitude
    if la < 37 and lo < 52 and not (lo > 34 and la > 12 and lo > 35.5 and la > 29) and (lo < 43 or la < 12):
        return "Africa (approx.)"
    if lo < 60 and la > 41 and not (lo > 40 and la < 44):
        return "Europe west of Urals (approx.)"
    return "Asia/Middle East/Oceania"
asia["geo"] = asia.apply(geo, axis=1)
R["asia_bbox_geography_rough"] = asia.geo.value_counts().to_dict()

# --- 3. NPP missingness: who gets dropped
asia["npp_missing"] = asia[MOD].isna().any(axis=1)
us["npp_missing"] = us[MOD].isna().any(axis=1)
igbp = {1: "ENF", 2: "EBF", 3: "DNF", 4: "DBF", 5: "MF", 6: "CSH", 7: "OSH", 8: "WSA", 9: "SAV", 10: "GRA",
        11: "WET", 12: "CRO", 13: "URB", 14: "CVM", 15: "SNO", 16: "BAR", 17: "WAT"}
for name, df in [("asia", asia), ("us", us)]:
    lc = df.landcover.map(igbp).fillna("NA")
    tab = pd.crosstab(lc, df.npp_missing)
    R[f"npp_missing_by_igbp_{name}"] = {k: {"kept": int(v.get(False, 0)), "dropped": int(v.get(True, 0))}
                                        for k, v in tab.iterrows()}
    R[f"logrs_kept_vs_dropped_{name}"] = [float(df.loc[~df.npp_missing, T].mean()),
                                          float(df.loc[df.npp_missing, T].mean())]

# --- 4. clay correlation with bootstrap CI
def corr_ci(x, y, f, n=5000, seed=1):
    rng = np.random.default_rng(seed); m = ~(np.isnan(x) | np.isnan(y)); x, y = x[m], y[m]
    bs = [f(x[i], y[i])[0] for i in (rng.integers(0, len(x), len(x)) for _ in range(n))]
    return dict(n=int(len(x)), r=float(f(x, y)[0]), p=float(f(x, y)[1]),
                ci=[float(np.quantile(bs, .025)), float(np.quantile(bs, .975))])
R["clay_vs_logrs"] = {reg: {"pearson": corr_ci(df.clay.values, df[T].values, pearsonr),
                            "spearman": corr_ci(df.clay.values, df[T].values, spearmanr)}
                      for reg, df in [("asia", asia), ("us", us)]}

# --- 5. spatial autocorrelation of log Rs (binned semivariance, Asia and US)
def semivar(df, bins=(0, 25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2000)):
    la, lo, z = df.latitude.values, df.longitude.values, df[T].values
    i, j = np.triu_indices(len(z), 1)
    d = hav_km(la[i], lo[i], la[j], lo[j]); g = 0.5 * (z[i] - z[j]) ** 2
    out = []
    for a, b in zip(bins[:-1], bins[1:]):
        m = (d >= a) & (d < b)
        out.append(dict(bin_km=f"{a}-{b}", n_pairs=int(m.sum()), gamma=float(g[m].mean()) if m.any() else None))
    return dict(sill_var=float(z.var()), bins=out)
R["semivariogram_logrs"] = {"asia": semivar(asia.dropna(subset=[T])), "us": semivar(us.dropna(subset=[T]))}

# --- 6. F+NPP: site vs spatial-block bootstrap on the US test set; residual autocorrelation
a = asia.dropna(subset=[T] + BIO + MOD).reset_index(drop=True)
u = us.dropna(subset=[T] + BIO + MOD).reset_index(drop=True)
m = xgb.XGBRegressor(**P_FNPP); m.fit(a[BIO + MOD].to_numpy("float32"), a[T].to_numpy("float32"))
pu = m.predict(u[BIO + MOD].to_numpy("float32")); yu = u[T].to_numpy("float32")
R["fnpp_r2_check"] = float(r2_score(yu, pu))
rng = np.random.default_rng(42)
blk_r2 = {}
for deg in [1.0, 2.0, 5.0]:
    blocks = (np.floor(u.longitude / deg).astype(int).astype(str) + "_" + np.floor(u.latitude / deg).astype(int).astype(str)).values
    ub = np.unique(blocks); idx_by = {b: np.where(blocks == b)[0] for b in ub}
    bs = []
    for _ in range(2000):
        pick = rng.choice(ub, len(ub), replace=True)
        idx = np.concatenate([idx_by[b] for b in pick]); bs.append(r2_score(yu[idx], pu[idx]))
    blk_r2[f"{deg}deg"] = dict(n_blocks=int(len(ub)), ci=[float(np.quantile(bs, .025)), float(np.quantile(bs, .975))])
R["fnpp_block_bootstrap_ci"] = blk_r2
res = yu - pu
R["fnpp_us_residual_semivariogram"] = semivar(u.assign(**{T: res}))

# --- 7. reverse direction US -> Asia (preview, same params, no tuning)
for name, feats, P in [("F", BIO, P_F), ("F+NPP", BIO + MOD, P_FNPP)]:
    aa = asia.dropna(subset=[T] + feats); uu = us.dropna(subset=[T] + feats)
    mm = xgb.XGBRegressor(**P); mm.fit(uu[feats].to_numpy("float32"), uu[T].to_numpy("float32"))
    R[f"reverse_US_to_Asia_{name}"] = dict(n_train=len(uu), n_test=len(aa),
                                           r2=float(r2_score(aa[T], mm.predict(aa[feats].to_numpy("float32")))))

# --- 8. feature-space extrapolation: share of US sites outside Asia range (per feature, and any)
rng_out = {}
anyout = np.zeros(len(u), bool)
for f in BIO + MOD:
    lo, hi = a[f].quantile([0.01, 0.99]); o = (u[f] < lo) | (u[f] > hi); anyout |= o.values
    rng_out[f] = float(o.mean())
R["fnpp_us_outside_asia_1_99pct"] = dict(per_feature=rng_out, any=float(anyout.mean()))
R["fnpp_r2_inside_vs_outside"] = dict(inside_n=int((~anyout).sum()), inside_r2=float(r2_score(yu[~anyout], pu[~anyout])),
                                      outside_n=int(anyout.sum()), outside_r2=float(r2_score(yu[anyout], pu[anyout])))

(OUT / "audit.json").write_text(json.dumps(R, indent=2, default=str))
print(json.dumps(R, indent=1, default=str))
