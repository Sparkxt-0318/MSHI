import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import BallTree
from sklearn.metrics import r2_score
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V3, PROC, SRDB, CD = sys.argv[1:5]
r = pd.read_parquet(f"{V3}/records_v3.parquet"); s = pd.read_csv(SRDB, low_memory=False)
rep = pd.concat([pd.read_parquet(f"{PROC}/training_features_v2.parquet"), pd.read_parquet(f"{PROC}/us_validation_features_v2.parquet")]).dropna(subset=["bio01", "bio12"])
tree = BallTree(np.radians(rep[["latitude", "longitude"]].values), metric="haversine")
K = 12.011 * 31_536_000.0 / 1e6
q = pd.read_csv(f"{CD}/cosore_ports_diag.csv", keep_default_na=False); q = q[q.qual.astype(str) == "True"].copy(); q["mean_drop"] = q.mean_drop.astype(float)
good = q[(q.msmt_var == "Rs") & (q.treatment == "None")]
pm = pd.read_csv(f"{CD}/cosore_port_monthly.csv"); M = [f"m{m:02d}" for m in range(1, 13)]
partial = set(pm.groupby("ds")[M].apply(lambda x: ~x.notna().any().all()).loc[lambda z: z].index)
fixed = good[~good.ds.isin(partial)].groupby("ds").mean_drop.mean() * K   # Rs/None ports, outliers dropped, full-year only
def sites(recs):
    recs = recs.reset_index(drop=True)
    X = np.radians(recs[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(recs), len(recs))), directed=False)
    recs = recs.assign(site=lab, row=recs.rec_id.str.extract(r"srdb_(\d+)$")[0].astype(float))
    recs = recs.join(s[["MAT", "MAP"]], on="row")
    return recs.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"), MAT=("MAT", "mean"), MAP=("MAP", "mean"),
                                    continent=("continent", lambda x: x.mode().iat[0]))
base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].copy()
qc["ds"] = qc.rec_id.str.replace("cosore_", "", regex=False)
v = qc.copy(); m = v.src.eq("cosore"); v.loc[m, "rs"] = v.loc[m, "ds"].map(fixed); v = v[~(m & v.rs.isna())]; v["log_rs"] = np.log(v.rs)
for tag, recs in [("as built", qc), ("COSORE fixed (Rs/None ports, outliers dropped, full-year only)", v)]:
    st = sites(recs)
    A = st[st.continent == "Asia"].copy(); d, i = tree.query(np.radians(A[["lat", "lon"]].values), k=1)
    A["bio01"], A["bio12"] = rep.bio01.values[i[:, 0]], rep.bio12.values[i[:, 0]]; A = A[d[:, 0] * 6371 <= 10]
    mdl = LinearRegression().fit(np.c_[A.bio01, np.log(A.bio12)], A.log_rs)
    E = st[(st.continent == "Europe")].dropna(subset=["MAT", "MAP"]); E = E[E.MAP > 0]
    p = mdl.predict(np.c_[E.MAT, np.log(E.MAP)])
    print(f"{tag}: Asia n={len(A)} b_T={mdl.coef_[0]:.4f} b_lnP={mdl.coef_[1]:.4f}; Europe(proxy MAT/MAP) n={len(E)} R2={r2_score(E.log_rs, p):.4f}")
