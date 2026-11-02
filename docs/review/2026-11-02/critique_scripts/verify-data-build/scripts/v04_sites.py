import sys, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V = sys.argv[1]
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet"); g = pd.read_csv(f"{V}/out/coord_geodesic.csv").set_index("rec_id")
label_only = {("Congo", "Democratic Republic of the Congo"), ("China", "Taiwan"), ("Mongolia", "China"), ("Italy", "Malta"),
              ("New Zealand", "New Caledonia"), ("Norway", "Estonia"), ("Indonesia", "Malaysia")}
def sites(r):
    base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
    X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
    st = qc.assign(site=lab).groupby("site").continent.agg(lambda x: x.mode().iat[0])
    return len(base), len(qc), st.value_counts().to_dict()
print("as built      :", sites(rec))
r1 = rec.copy(); m = r1.rec_id.isin(g.index); r1.loc[m, "f_coord"] = r1.loc[m, "rec_id"].map(lambda k: bool((g.loc[k, "d_geo"] > 100) and not g.loc[k, "terr"]))
print("geodesic 100km:", sites(r1))
r2 = r1.copy(); lo = r2.rec_id.map(lambda k: k in g.index and (g.loc[k, "Country"], g.loc[k, "geo"]) in label_only or (k in g.index and str(g.loc[k, "Site_name"]) == "Catchacoma"))
r2.loc[lo, "f_coord"] = False
print("geodesic + keep label-only:", sites(r2), " label-only records kept:", int(lo.sum()))
