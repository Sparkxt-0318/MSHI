"""Misc checks used in the transfer-noise critique. Usage: python -I probe_misc.py SCRATCH_DIR NE_DIR
(1) singleton-site variance vs variance components; (2) within-site pairs by ecosystem type;
(3) 5-deg block counts and fold sizes per continent; (4) E4 site unit vs original 0.05-deg cells; (5) Greenland share of E5 grid."""
import sys, numpy as np, pandas as pd, geopandas as gpd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
W, NE = sys.argv[1:3]
def clus(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
R = pd.read_parquet(f"{W}/data/records_v3.parquet"); base = R[~R.f_offland & ~R.f_coord]
q = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True); q["site"] = clus(q)
n = q.groupby("site").log_rs.transform("size"); sing = q[n == 1]
print("(1) singletons", len(sing), "var", round(sing.log_rs.var(), 3), {c: round(sing[sing.continent == c].log_rs.var(), 3) for c in ["Asia", "Europe", "North America"]})
P = []
for sid, g in q.groupby("site"):
    if len(g) < 2: continue
    v = g.log_rs.values; e = g.Ecosystem_type.astype(str).values
    for i in range(len(v)):
        for j in range(i + 1, len(v)): P.append((0.5 * (v[i] - v[j]) ** 2, e[i] == e[j]))
P = pd.DataFrame(P, columns=["h", "same"]); print("(2) pairs", len(P), "diff-eco share", round((~P.same).mean(), 3), "semivar diff/same", round(P[~P.same].h.mean(), 3), round(P[P.same].h.mean(), 3))
S = pd.read_parquet(f"{W}/data/sites_v3_qc.parquet")
for c in ["Asia", "Europe", "North America"]:
    u = S[S.continent == c]; b = (np.floor(u.lon / 5).astype(int).astype(str) + "_" + np.floor(u.lat / 5).astype(int).astype(str)).values; ub = np.unique(b)
    sz = []
    for seed in (42, 43, 44):
        uu = ub.copy(); np.random.default_rng(seed).shuffle(uu); sz.append([int(np.isin(b, vb).sum()) for vb in np.array_split(uu, 5)])
    print("(3)", c, "blocks", len(ub), "fold sizes", sz)
r = base.reset_index(drop=True); r["site"] = clus(r); r["cell"] = list(zip((r.lon / 0.05).round().astype(int), (r.lat / 0.05).round().astype(int)))
s = r.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), ncell=("cell", "nunique"))
for nm, m in [("Asia box", s.lon.between(25, 180) & s.lat.between(-10, 80)), ("US box", s.lon.between(-125, -66) & s.lat.between(24, 50))]:
    print("(4)", nm, "E4 clusters", int(m.sum()), "0.05deg cells", int(s[m].ncell.sum()))
lon, lat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-59.75, 84, 0.5)); g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
j = gpd.sjoin(gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326), gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")[["ADMIN", "geometry"]], predicate="within")
j = j[~j.index.duplicated()]; j["akm2"] = (111.32 * 0.5) ** 2 * np.cos(np.radians(j.lat)); gl = j.ADMIN.eq("Greenland"); arc = j.lat.between(66.5, 84)
print("(5) Greenland share of grid", round(j[gl].akm2.sum() / j.akm2.sum(), 3), "of Arctic band", round(j[gl & arc].akm2.sum() / j[arc].akm2.sum(), 3))
