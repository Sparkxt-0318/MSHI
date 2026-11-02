"""Approximate the locked OLS-TP Asia->Europe score with SRDB-reported MAT/MAP as proxies for WorldClim bio01/bio12
(WorldClim is not reachable), to measure the influence of the non-European 'Europe' sites (French Guiana, Canaries)."""
import sys, numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
SRDB, V3, PROC = sys.argv[1], sys.argv[2], sys.argv[3]
s = pd.read_csv(SRDB, low_memory=False)
r = pd.read_parquet(f"{V3}/records_v3.parquet")
# proxy quality: repo Asia/US tables (WorldClim) vs SRDB MAT/MAP by original row index
rep = pd.concat([pd.read_parquet(f"{PROC}/training_features_v2.parquet"), pd.read_parquet(f"{PROC}/us_validation_features_v2.parquet")])
rep = rep[rep.source == "srdb"].copy(); rep["row"] = rep.site_id.str.extract(r"(\d+)$").astype(int)
j = rep.join(s[["MAT", "MAP"]], on="row").dropna(subset=["MAT", "MAP", "bio01", "bio12"])
print(f"proxy check (n={len(j)}): r(MAT,bio01)={j.MAT.corr(j.bio01):.3f}  r(lnMAP,ln bio12)={np.log(j.MAP).corr(np.log(j.bio12)):.3f}")
# site table rebuild with record->site labels (same algorithm as build_sites_v3.to_sites)
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab
qc["row"] = qc.rec_id.str.extract(r"srdb_(\d+)$")[0].astype(float)
qc = qc.join(s[["MAT", "MAP"]], on="row")
st = qc.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"), MAT=("MAT", "mean"), MAP=("MAP", "mean"),
                            continent=("continent", lambda x: x.mode().iat[0]), country=("geo_country", lambda x: x.mode().iat[0]))
st = st.dropna(subset=["MAT", "MAP"]); st = st[st.MAP > 0]
A, E = st[st.continent == "Asia"], st[st.continent == "Europe"].copy()
m = LinearRegression().fit(np.c_[A.MAT, np.log(A.MAP)], A.log_rs)
print(f"Asia proxy fit n={len(A)} coef MAT={m.coef_[0]:.4f} lnMAP={m.coef_[1]:.4f}")
E["p"] = m.predict(np.c_[E.MAT, np.log(E.MAP)])
E["nonEU"] = (E.lon < -25) | (E.lat < 34)
print(E[E.nonEU][["lat", "lon", "country", "MAT", "MAP", "log_rs", "p"]].round(3).to_string())
def rep_(x, tag):
    y, p = x.log_rs.values, x.p.values
    rng = np.random.default_rng(42); bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(2000))]
    print(f"{tag}: n={len(x)} R2={r2_score(y, p):.3f} site-boot CI [{np.quantile(bs,.025):.3f}, {np.quantile(bs,.975):.3f}]  sd(y)={y.std():.3f}")
rep_(E, "Europe (as built, proxies)")
rep_(E[~E.nonEU], "Europe excl. French Guiana + Canaries")
rep_(E[~((E.lon < -25) & (E.lat < 10))], "Europe excl. French Guiana only")
