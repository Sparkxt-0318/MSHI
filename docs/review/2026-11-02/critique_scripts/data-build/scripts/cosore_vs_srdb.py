import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V3, CD = sys.argv[1], sys.argv[2]
pd.set_option("display.width", 250)
r = pd.read_parquet(f"{V3}/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord].reset_index(drop=True)
X = np.radians(base[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(base), len(base))), directed=False)
base["site"] = lab
pm = pd.read_csv(f"{CD}/cosore_port_monthly.csv"); M = [f"m{m:02d}" for m in range(1, 13)]
full12 = pm.groupby("ds")[M].apply(lambda x: x.notna().any().all())
diag = pd.read_csv(f"{CD}/cosore_ports_diag.csv", keep_default_na=False)
q = diag[diag.qual.astype(str) == "True"]
nonrs = q.groupby("ds").apply(lambda g: bool(((g.msmt_var != "Rs") | (g.treatment != "None")).any()))
out = []
for sid, g in base.groupby("site"):
    c = g[g.src == "cosore"]; s = g[g.src == "srdb"]
    if len(c) == 0 or len(s) == 0: continue
    for _, x in c.iterrows():
        ds = x.rec_id.replace("cosore_", "")
        out.append(dict(ds=ds, cont=x.continent, cos_rs=round(x.rs), srdb_n=len(s), srdb_gmean=round(float(np.exp(s.log_rs.mean()))),
                        dlog=round(x.log_rs - s.log_rs.mean(), 3), full_year=bool(full12.get(ds, False)), nonRs_ports=bool(nonrs.get(ds, False))))
o = pd.DataFrame(out)
print(o.sort_values("dlog").to_string(index=False))
for k, g in o.groupby("full_year"):
    print(f"full_year={k}: n={len(g)} mean dlog={g.dlog.mean():.3f} median={g.dlog.median():.3f}")
# COSORE presence by continent (QC and repo)
for tag in ["qc", "repo"]:
    st = pd.read_parquet(f"{V3}/sites_v3_{tag}.parquet")
    print(tag, "sites with >=1 COSORE record by continent:", st[st.n_cosore > 0].continent.value_counts().to_dict(),
          "; COSORE-only sites:", st[(st.n_cosore > 0) & (st.n_cosore == st.n_rec)].continent.value_counts().to_dict())
