import sys, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V = sys.argv[1]
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet"); s = pd.read_csv(f"{V}/out/cosore/site_season.csv", index_col=0)
full = (s.max_months == 12)
for tag in ["repo", "qc"]:
    base = rec[~rec.f_offland & ~rec.f_coord]
    rr = base if tag == "repo" else base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)]
    rr = rr.reset_index(drop=True)
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr), len(rr))), directed=False)
    rr = rr.assign(site=lab)
    out = []
    for _, c in rr[rr.src == "cosore"].iterrows():
        sr = rr[(rr.site == c.site) & (rr.src == "srdb")]
        if len(sr) == 0: continue
        ds = c.rec_id.replace("cosore_", "")
        out.append(dict(ds=ds, full=bool(full[ds]), cos=c.rs, srdb_mean=float(np.exp(sr.log_rs.mean())), n_srdb=len(sr), d=c.log_rs - sr.log_rs.mean()))
    o = pd.DataFrame(out)
    for f, g in o.groupby("full"):
        print(f"[{tag}] {'full-year' if f else 'partial-year'} COSORE sites with co-located SRDB: n={len(g)} mean diff {g.d.mean():+.3f} median {g.d.median():+.3f}")
    print(o[~o.full].sort_values("d", ascending=False).head(6).round(2).to_string(index=False))
