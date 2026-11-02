"""PROXY ONLY: attach SRDB-reported MAT/MAP (study-reported, not WorldClim) to the exact locked-test sites,
by recomputing the 5-km connected components exactly as build_sites_v3.to_sites does."""
import sys
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
W, SRDB = sys.argv[1:3]
r = pd.read_parquet(f"{W}/out/v3/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site_id"] = [f"v3qc_{i:05d}" for i in lab]
s = pd.read_csv(SRDB, low_memory=False, usecols=["MAT", "MAP"])
s["rec_id"] = "srdb_" + s.index.astype(str)
qc = qc.merge(s, on="rec_id", how="left")
qc.loc[qc.MAP <= 0, "MAP"] = np.nan
g = qc.groupby("site_id").agg(mat=("MAT", "mean"), map=("MAP", "mean"), log_rs_chk=("log_rs", "mean"))
for nm in ["asia_384", "europe_235"]:
    d = pd.read_parquet(f"{W}/out/{nm}.parquet").merge(g, left_on="site_id", right_index=True, how="left")
    assert np.allclose(d.log_rs, d.log_rs_chk)
    d.to_parquet(f"{W}/out/{nm}_proxy.parquet")
    print(nm, len(d), "with proxy MAT&MAP:", int(d[["mat", "map"]].notna().all(1).sum()))
