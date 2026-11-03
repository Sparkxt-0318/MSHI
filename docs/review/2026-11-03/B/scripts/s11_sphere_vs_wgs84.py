"""Docstring claim: spherical (R = 6371 km) distances are within -0.45% to +0.56% of WGS84 geodesics for 1-3,000 km.
And: kNNDM on WGS84 distances (knndm_core) gives the same q and split as on spherical ones, for the real site
coordinates of Asia, Europe and North America with the Natural-Earth stand-in domain."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from pyproj import Geod
from mshi.analysis import knndm as kn
from mshi.analysis import transfer as T
from mshi.config import load_config
geod = Geod(ellps="WGS84")
rng = np.random.default_rng(3)
lon1, lat1 = rng.uniform(-180, 180, 200000), np.degrees(np.arcsin(rng.uniform(-1, 1, 200000)))
az = rng.uniform(0, 360, 200000); dist = rng.uniform(1e3, 3e6, 200000)
lon2, lat2, _ = geod.fwd(lon1, lat1, az, dist)
sph = kn.haversine_km(lon1, lat1, lon2, lat2, 6371.0) * 1000
rel = sph / dist - 1
print(f"spherical/WGS84 - 1 over 200,000 random pairs 1-3000 km: min {rel.min()*100:.3f}%  max {rel.max()*100:.3f}%")
cfg = load_config(); K = cfg["phase2"]["within"]["knndm"]
g = pd.read_parquet("ne_grid_0p5.parquet")
d = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet").sort_values("site_id", kind="mergesort")
def wgs(a, b):
    A = np.repeat(a, len(b), axis=0); B = np.tile(b, (len(a), 1))
    return (geod.inv(A[:, 0], A[:, 1], B[:, 0], B[:, 1])[2] / 1000).reshape(len(a), len(b))
for c in ["Asia", "Europe", "North America"]:
    x = d.loc[d.continent_geo == c, ["lon", "lat"]].to_numpy(float)
    dom = T.prediction_domain(g, c, K)
    f1, i1 = kn.knndm_folds(x, dom, 5, 0.5, "hierarchical", 42, earth_radius_km=6371.0, nk_len=100)
    D = wgs(x, x); np.fill_diagonal(D, 0); D = (D + D.T) / 2
    gij = wgs(dom, x).min(axis=1)
    Dn = D + np.diag(np.full(len(x), np.inf)); gj = Dn.min(axis=1)
    f2, r2 = kn.knndm_core(D, gij, gj, x, 5, 0.5, 42, 100, "ward.D2", 0.05)
    same = len(set(zip(f1.tolist(), f2.tolist()))) == len(np.unique(f1))
    print(f"{c}: q sphere {i1['q']} vs WGS84 {r2['q']}; same split {same}; W {i1['W']:.1f} vs {r2['W']:.1f}")
