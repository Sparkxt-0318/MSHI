"""Exploratory E4: why does v3 transfer (Asia->NA) so much better than the original pipeline? Ablation.
Model fixed: XGB (locked params) on C8 bioclim. Factors:
  target: site mean of all records vs one arbitrary record per site (lowest SRDB row, as in the original dedup)
  regions: continents (Natural Earth) vs original bounding boxes
  features: WorldClim 2.5' (v3) vs original committed features (only possible on the original 889 sites)
"""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb, rasterio
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
from sklearn.metrics import r2_score

V3, DL, REPO, OUT = sys.argv[1:5]
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
                r2_seed_mean=round(float(np.mean(r2s)), 3))


def sample(path, lon, lat):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)
    return np.where(v < -1e30, np.nan, v)


r = pd.read_parquet(f"{V3}/records_v3.parquet")
r = r[~r.f_offland & ~r.f_coord].reset_index(drop=True)
X = np.radians(r[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
r["site"] = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(r),) * 2), directed=False)[1]
r["order"] = np.where(r.src == "cosore", -1, r.rec_id.str.replace("srdb_", "").str.replace(r"\D", "", regex=True).replace("", "-1").astype(int))
g = r.groupby("site")
sites = g.agg(lat=("lat", "mean"), lon=("lon", "mean"), y_mean=("log_rs", "mean"), continent=("continent", lambda x: x.mode().iat[0]))
first = r.sort_values(["src", "order"]).groupby("site").first()   # cosore before srdb, then lowest row (original rule)
sites["y_single"] = first.log_rs; sites["lat1"], sites["lon1"] = first.lat, first.lon
for i, k in zip([1, 4, 5, 6, 12, 14, 15, 17], C8):
    sites[k] = sample(f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif", sites.lon1.values, sites.lat1.values)
box_asia = sites.lon.between(25, 180) & sites.lat.between(-10, 80)
box_us = sites.lon.between(-125, -66) & sites.lat.between(24, 50)
R = {}
for tgt in ["y_mean", "y_single"]:
    s2 = sites.assign(y=sites[tgt])
    R[f"{tgt}|continents"] = fit_score(s2[s2.continent == "Asia"], s2[s2.continent == "North America"])
    R[f"{tgt}|boxes"] = fit_score(s2[box_asia], s2[box_us])

# original 889 sites: original targets with original features vs v3 (2.5') features
o_a = pd.read_parquet(f"{REPO}/data/processed/training_features_v2.parquet")
o_u = pd.read_parquet(f"{REPO}/data/processed/us_validation_features_v2.parquet")
for df in (o_a, o_u):
    df["y"] = df.log_rs_annual
R["original_sites|original_features"] = fit_score(o_a, o_u)
for df in (o_a, o_u):
    for i, k in zip([1, 4, 5, 6, 12, 14, 15, 17], C8):
        df[k] = sample(f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif", df.longitude.values, df.latitude.values)
R["original_sites|v3_features"] = fit_score(o_a, o_u)
# original sites, but target replaced by the v3 site mean of the matching cluster (nearest v3 site within 5 km)
tree = BallTree(np.radians(sites[["lat", "lon"]].values), metric="haversine")
for df in (o_a, o_u):
    dist, idx = tree.query(np.radians(df[["latitude", "longitude"]].values), k=1)
    df["y"] = np.where(dist[:, 0] * 6371 < 5, sites.y_mean.values[idx[:, 0]], np.nan)
R["original_sites|v3_features|site_mean_target"] = fit_score(o_a, o_u)
json.dump(R, open(OUT, "w"), indent=1)
for k, v in R.items(): print(f"{k:50s} {v}")
