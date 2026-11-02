"""Approximate N2b plot-forest coefficient (exp_forest_bias.py:23-31,60-62) with WorldClim bio01/bio12 borrowed from the
nearest original repo site (<=10 km), as built vs with COSORE fixes (Rs/None ports only; drop datasets with no such port;
drop instead of clip; drop partial-year datasets)."""
import sys, numpy as np, pandas as pd, rasterio, statsmodels.formula.api as smf
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V = sys.argv[1]; K = 12.011 * 31_536_000.0 / 1e6
P = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs"
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
pr = pd.read_csv(f"{V}/out/cosore/ports_diag.csv", keep_default_na=False, na_values=[""]); se = pd.read_csv(f"{V}/out/cosore/site_season.csv", index_col=0)
ok = pr[(pr.msmt == "Rs") & (pr.trt == "None")]
fix_rs = (ok.groupby("ds").drop_mean.mean() * K)
rep = pd.concat([pd.read_parquet(f"{P}/processed/training_features_v2.parquet"), pd.read_parquet(f"{P}/processed/us_validation_features_v2.parquet")]).dropna(subset=["bio01", "bio12"])
tree = BallTree(np.radians(rep[["latitude", "longitude"]].values), metric="haversine")
def sites(r):
    base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
    X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
    return qc.assign(site=lab).groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"),
        ecosystem=("Ecosystem_type", lambda x: x.mode().iat[0] if x.notna().any() else np.nan), continent=("continent", lambda x: x.mode().iat[0]))
def n2b(st):
    d = st.copy(); rp = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest", "Mixed forests": "Forest"}
    d["plot_forest"] = d.ecosystem.replace(rp).eq("Forest").astype(int)
    dist, i = tree.query(np.radians(d[["lat", "lon"]].values), k=1); d["bio01"] = rep.bio01.values[i[:, 0]]; d["bio12"] = rep.bio12.values[i[:, 0]]
    d.loc[dist[:, 0] * 6371 > 10, ["bio01", "bio12"]] = np.nan; d["lnP"] = np.log(d.bio12)
    inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
    d = d[inbox & d.continent.isin(["Asia", "North America"])].dropna(subset=["log_rs", "bio01", "lnP"]).copy()
    with rasterio.open(f"{P}/modis/landcover_igbp_2023.tif") as s: code = np.array([v[0] for v in s.sample(list(zip(d.lon, d.lat)))], float)
    d = d[code > 0]
    m = smf.ols("log_rs ~ bio01 + lnP + plot_forest + C(continent)", data=d).fit()
    return len(d), round(m.params.plot_forest, 4), round(d.plot_forest.mean(), 3)
print("as built (borrowed WorldClim):", n2b(sites(rec)), " [handoff N2b: n=578, coef 0.126, share 0.685]")
r = rec.copy(); c = r.src == "cosore"; ds = r.loc[c, "rec_id"].str.replace("cosore_", "")
r.loc[c, "rs"] = ds.map(lambda k: fix_rs.get(k, np.nan)).values; r = r[~(c & r.rs.isna())].copy(); r["log_rs"] = np.log(r.rs)
print("COSORE Rs/None ports only, drop-not-clip, no-Rs datasets removed:", n2b(sites(r)))
r2 = r[~((r.src == "cosore") & r.rec_id.str.replace("cosore_", "").isin(se.index[se.max_months < 12]))]
print("  + partial-year COSORE datasets removed:", n2b(sites(r2)))
