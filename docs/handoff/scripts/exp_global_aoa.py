"""Exploratory E5: how much of the land surface and of the global Rs flux lies outside the area of applicability (AOA)
of an SRDB/COSORE-trained model? (Meyer & Pebesma 2021 DI, threshold from spatial-block CV training DI.)
Model: XGB on C8 bioclim (globally available), trained (a) on all v3-QC sites and (b) on Asia only.
Grid: 0.5 deg land cells (WorldClim 2.1 2.5' sampled at cell centres). Also returns DI-binned transfer error on NA.
"""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb, rasterio
from scipy.spatial import cKDTree
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score

FEAT, DL, OUT = sys.argv[1:4]
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]; IDX = [1, 4, 5, 6, 12, 14, 15, 17]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
         reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0, random_state=0)
d = pd.read_parquet(FEAT).dropna(subset=C8 + ["log_rs"]).reset_index(drop=True)

lon, lat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-59.75, 84, 0.5))
g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
for i, k in zip(IDX, C8):
    with rasterio.open(f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif") as s:
        v = np.array([x[0] for x in s.sample(list(zip(g.lon, g.lat)))], float)
    g[k] = np.where(v < -1e30, np.nan, v)
g = g.dropna().reset_index(drop=True)
g["area_km2"] = (111.32 * 0.5) ** 2 * np.cos(np.radians(g.lat))
g = g[g.bio05 > -50]  # drop ice-sheet fill artefacts if any


def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]


def aoa(train, targets):
    X = train[C8].to_numpy(float); y = train.log_rs.values
    m = xgb.XGBRegressor(**P).fit(X, y)
    w = permutation_importance(m, X, y, n_repeats=10, random_state=0).importances_mean.clip(min=0); w = w / w.sum()
    mu, sd = X.mean(0), X.std(0)
    Z = (X - mu) / sd * w
    sub = Z[np.random.default_rng(0).choice(len(Z), min(len(Z), 1500), replace=False)]
    dbar = np.mean([np.linalg.norm(sub[i] - sub[j]) for i, j in zip(*np.triu_indices(len(sub), 1))][:400000])
    tdi = np.empty(len(Z))
    for tr, va in folds(train):
        tdi[va] = cKDTree(Z[tr]).query(Z[va])[0] / dbar
    q1, q3 = np.quantile(tdi, [.25, .75]); thr = tdi[tdi <= q3 + 1.5 * (q3 - q1)].max()
    tree = cKDTree(Z); out = {}
    for name, df in targets.items():
        Zt = (df[C8].to_numpy(float) - mu) / sd * w
        out[name] = (tree.query(Zt)[0] / dbar, m.predict(df[C8].to_numpy(float)))
    return m, thr, out, dict(zip(C8, np.round(w, 3)))


R = {}
for tag, train in [("all_sites", d), ("asia_only", d[d.continent == "Asia"].reset_index(drop=True))]:
    na = d[d.continent == "North America"].reset_index(drop=True)
    m, thr, out, w = aoa(train, {"grid": g, "na": na})
    di, pred = out["grid"]; inside = di <= thr
    rs = np.exp(pred)  # g C m-2 yr-1
    flux = rs * g.area_km2.values * 1e6 / 1e15  # Pg C yr-1
    R[tag] = dict(n_train=len(train), threshold=float(thr), importance_weights=w,
                  global_rs_PgC=round(float(flux.sum()), 1),
                  land_area_frac_outside=round(float(g.area_km2[~inside].sum() / g.area_km2.sum()), 3),
                  rs_flux_frac_outside=round(float(flux[~inside].sum() / flux.sum()), 3))
    g[f"di_{tag}"] = di; g[f"inside_{tag}"] = inside; g[f"rs_{tag}"] = rs
    if tag == "asia_only":
        dna, pna = out["na"]; y = na.log_rs.values; ins = dna <= thr
        R[tag]["NA_frac_inside"] = round(float(ins.mean()), 3)
        R[tag]["NA_inside"] = dict(n=int(ins.sum()), r2=round(float(r2_score(y[ins], pna[ins])), 3), rmse=round(float(np.sqrt(np.mean((y[ins] - pna[ins]) ** 2))), 3))
        R[tag]["NA_outside"] = dict(n=int((~ins).sum()), r2=round(float(r2_score(y[~ins], pna[~ins])), 3), rmse=round(float(np.sqrt(np.mean((y[~ins] - pna[~ins]) ** 2))), 3))
        q = np.quantile(dna, [0, 1 / 3, 2 / 3, 1])
        R[tag]["NA_rmse_by_DI_tercile"] = [round(float(np.sqrt(np.mean(((y - pna)[(dna >= a) & (dna <= b)]) ** 2))), 3) for a, b in zip(q[:-1], q[1:])]
    # by continent of land (rough: lon/lat boxes are avoided; use nearest site continent is wrong) -> report by latitude band
    band = pd.cut(g.lat, [-60, -23.5, 23.5, 50, 66.5, 84], labels=["S temperate", "Tropics", "N temperate", "N boreal", "Arctic"])
    R[tag]["frac_area_outside_by_lat_band"] = g.assign(o=~inside).groupby(band, observed=True).apply(
        lambda x: round(float(x.area_km2[x.o].sum() / x.area_km2.sum()), 3)).to_dict()
g.to_parquet(OUT.replace(".json", "_grid.parquet"), index=False)
json.dump(R, open(OUT, "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
