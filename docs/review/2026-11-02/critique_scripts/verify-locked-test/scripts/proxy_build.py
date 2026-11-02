"""PROXY covariates (not the locked features): site-mean SRDB-reported MAT and MAP for the exact locked-test rows."""
import sys
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
V3, SRDB = sys.argv[1], sys.argv[2]
r = pd.read_parquet(V3 + "/records_v3.parquet"); base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True).copy()
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc),) * 2), directed=False)[1]
qc["site_id"] = [f"v3qc_{i:05d}" for i in lab]
s = pd.read_csv(SRDB, low_memory=False)
sr = qc[qc.src == "srdb"].copy(); idx = sr.rec_id.str.replace("srdb_", "").astype(int).values
sr["MAT"] = s.MAT.values[idx]; sr["MAP"] = s.MAP.values[idx]
cl = sr.groupby("site_id")[["MAT", "MAP"]].mean()
for nm in ["asia_384", "europe_235"]:
    d = pd.read_parquet(f"out/{nm}.parquet").merge(cl, left_on="site_id", right_index=True, how="left")
    print(nm, len(d), "with MAT&MAP:", int(d[["MAT", "MAP"]].notna().all(1).sum()))
    d.to_parquet(f"out/{nm}_proxy.parquet")
