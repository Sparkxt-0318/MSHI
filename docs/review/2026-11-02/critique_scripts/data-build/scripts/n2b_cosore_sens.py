"""Approximate N2b (exp_forest_bias.py) plot-forest coefficient on rebuilt v3 QC sites, with WorldClim bio01/bio12
borrowed from the nearest ORIGINAL repo site (training/us_validation_features_v2, same boxes), then test sensitivity
to the COSORE aggregation problems. Approximation: repo climate resolution differs from v3's 2.5'."""
import sys, warnings, numpy as np, pandas as pd, rasterio
warnings.filterwarnings("ignore")
import statsmodels.formula.api as smf
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V3, PROC, LC, CD = sys.argv[1:5]
r = pd.read_parquet(f"{V3}/records_v3.parquet")
rep = pd.concat([pd.read_parquet(f"{PROC}/training_features_v2.parquet"), pd.read_parquet(f"{PROC}/us_validation_features_v2.parquet")]).dropna(subset=["bio01", "bio12"])
tree = BallTree(np.radians(rep[["latitude", "longitude"]].values), metric="haversine")
diag = pd.read_csv(f"{CD}/cosore_ports_diag.csv", keep_default_na=False); q = diag[diag.qual.astype(str) == "True"]
bad_ports = set(q[(q.msmt_var != "Rs") | (q.treatment != "None")].ds)
pm = pd.read_csv(f"{CD}/cosore_port_monthly.csv"); M = [f"m{m:02d}" for m in range(1, 13)]
partial = set(pm.groupby("ds")[M].apply(lambda x: ~x.notna().any().all()).loc[lambda s: s].index)
K = 12.011 * 31_536_000.0 / 1e6
qq = q.copy(); qq["mean_clip"] = qq.mean_clip.astype(float)
ctl = qq[(qq.msmt_var == "Rs") & (qq.treatment == "None")].groupby("ds").mean_clip.mean() * K
RW = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest", "Mixed forests": "Forest"}

def build(recs):
    recs = recs.reset_index(drop=True)
    X = np.radians(recs[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(recs), len(recs))), directed=False)
    recs = recs.assign(site=lab)
    st = recs.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"),
                                  ecosystem=("Ecosystem_type", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
                                  continent=("continent", lambda x: x.mode().iat[0]), n_cos=("src", lambda x: int((x == "cosore").sum())))
    d, i = tree.query(np.radians(st[["lat", "lon"]].values), k=1)
    st["d_km"] = d[:, 0] * 6371; st["bio01"] = rep.bio01.values[i[:, 0]]; st["bio12"] = rep.bio12.values[i[:, 0]]
    st.loc[st.d_km > 10, ["bio01", "bio12"]] = np.nan
    st["plot_forest"] = st.ecosystem.replace(RW).eq("Forest").astype(int); st["lnP"] = np.log(st.bio12)
    inbox = (st.lon.between(25, 180) & st.lat.between(-10, 80)) | (st.lon.between(-125, -66) & st.lat.between(24, 50))
    st = st[inbox & st.continent.isin(["Asia", "North America"])].dropna(subset=["log_rs", "bio01", "lnP"]).copy()
    with rasterio.open(LC) as s: code = np.array([x[0] for x in s.sample(list(zip(st.lon, st.lat)))], float)
    return st[code > 0].copy()

def coef(st, nboot=500, seed=0):
    f = "log_rs ~ bio01 + lnP + plot_forest + C(continent)"
    b = smf.ols(f, data=st).fit().params.plot_forest
    rng = np.random.default_rng(seed); bs = [smf.ols(f, data=st.iloc[rng.integers(0, len(st), len(st))]).fit().params.plot_forest for _ in range(nboot)]
    return b, np.quantile(bs, [.025, .975])

base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].copy()
qc["ds"] = qc.rec_id.str.replace("cosore_", "", regex=False)
variants = {"as built (handoff logic)": qc}
v = qc.copy(); m = v.src.eq("cosore") & v.ds.isin(bad_ports)
v.loc[m, "rs"] = v.loc[m, "ds"].map(ctl); v = v[~(m & v.rs.isna())]; v["log_rs"] = np.log(v.rs)
variants["COSORE: Rs/no-treatment ports only"] = v
v2 = v.copy(); m2 = v2.src.eq("cosore") & v2.ds.isin(partial); variants["... and drop partial-year COSORE"] = v2[~m2]
variants["no COSORE at all"] = qc[qc.src.eq("srdb")]
for k, recs in variants.items():
    st = build(recs); b, ci = coef(st)
    print(f"{k:38s} n={len(st)} plot-forest share={st.plot_forest.mean():.3f}  coef={b:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]  (median nn dist {st.d_km.median():.2f} km)")
