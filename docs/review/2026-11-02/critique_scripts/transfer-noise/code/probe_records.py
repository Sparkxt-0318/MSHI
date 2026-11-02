import sys, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
W=sys.argv[1]
r = pd.read_parquet(f"{W}/data/records_v3.parquet")
print(r.columns.tolist())
r = r[~r.f_offland & ~r.f_coord].copy()
QC = ~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)
def cluster(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
rr = r[QC].reset_index(drop=True); rr["site"] = cluster(rr)
n = rr.groupby("site").size().sort_values(ascending=False)
print("sites", len(n), "multi", (n>=2).sum(), "records in multi", n[n>=2].sum())
print("top 10 site sizes", n.head(10).tolist())
# cluster spatial extent (max pairwise distance) for big clusters
from sklearn.metrics.pairwise import haversine_distances
ext = {}
for s, g in rr.groupby("site"):
    if len(g) < 2: continue
    X = np.radians(g[["lat","lon"]].drop_duplicates().values)
    ext[s] = haversine_distances(X).max()*6371 if len(X)>1 else 0.0
ext = pd.Series(ext)
print("cluster extent km quantiles", ext.quantile([.5,.9,.99,1]).round(1).to_dict(), "n>10km", (ext>10).sum(), "n>20km", (ext>20).sum())
# pair counts
pairs = n*(n-1)/2
print("total within-site pairs", pairs.sum(), "share from top5 sites", round(pairs.head(5).sum()/pairs.sum(),3), "top10", round(pairs.head(10).sum()/pairs.sum(),3))
# SSW share from top sites
m = rr.groupby("site").log_rs.transform("mean"); rr["dev2"] = (rr.log_rs-m)**2
ssw = rr.groupby("site").dev2.sum().reindex(n.index)
print("SSW share top10 sites", round(ssw.head(10).sum()/ssw.sum(),3), "records share top10", round(n.head(10).sum()/n[n>=2].sum(),3))
