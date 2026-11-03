"""Realistic configuration (k=5, maxp=0.5, nk_len=100, 4000 area-weighted prediction points, 230-390 clustered
sites over continent-sized boxes): port vs literal re-derivation. Also the error cases of s01."""
import sys, time
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
from mshi.analysis.grid import cell_area_km2
R = 6371.0

def domain(rng, lon, lat, m=4000, deg=0.5):
    LO, LA = np.meshgrid(np.arange(lon[0] + deg/2, lon[1], deg), np.arange(lat[0] + deg/2, lat[1], deg))
    cells = np.c_[LO.ravel(), LA.ravel()]
    w = cell_area_km2(cells[:, 1], deg, R)
    return cells[np.sort(rng.choice(len(cells), m, replace=True, p=w / w.sum()))]

def sites(rng, n, lon, lat, ncl, sd):
    cen = np.c_[rng.uniform(*lon, ncl), rng.uniform(*lat, ncl)]
    sizes = rng.dirichlet(np.ones(ncl) * 0.7) * n
    lab = rng.choice(ncl, n, p=sizes / sizes.sum())
    return cen[lab] + rng.normal(0, sd, (n, 2)) * rng.uniform(0.2, 2.0, ncl)[lab][:, None]

rng = np.random.default_rng(7)
boxes = {"Europe": ((-10, 40), (36, 70), 233), "Asia": ((60, 145), (5, 60), 386), "NorthAm": ((-125, -60), (25, 60), 246)}
t0 = time.time()
for rep in range(3):
    for name, (lon, lat, n) in boxes.items():
        pred = domain(rng, lon, lat)
        s = sites(rng, n, lon, lat, int(rng.integers(8, 40)), float(rng.uniform(0.2, 1.5)))
        f, info = kn.knndm_folds(s, pred, 5, 0.5, "hierarchical", 42, earth_radius_km=R, nk_len=100)
        r = rcast.knndm_geo(s, pred, 5, 0.5, 100, R=R, rand=kn.random_folds(n, 5, 42) + 1)
        same = (info["random_cv"] == r["random"]) and (r["random"] or (info["q"] == r["q"] and rcast.same_partition(f, r["clust"])))
        print(f"{name:8s} rep{rep} n={n} random={info['random_cv']} q={info['q']} vs {r.get('q')} W={info['W']:.4f} vs {r['W']:.4f} "
              f"p={info['ks']['p']:.3g} vs {r['ks_p']:.3g} partition_same={same} sizes={info['fold_sizes']}")
print(f"{time.time()-t0:.1f}s")
# the s01 error cases: does the re-derivation also find no valid configuration?
def sphere_box(rng, n, lon=(0.0, 30.0), lat=(35.0, 60.0)):
    s0, s1 = np.sin(np.radians(lat[0])), np.sin(np.radians(lat[1]))
    return np.c_[rng.uniform(*lon, n), np.degrees(np.arcsin(rng.uniform(s0, s1, n)))]
rng = np.random.default_rng(9)
nerr = agree = 0
for i in range(200):
    n = int(rng.integers(8, 60)); k = int(rng.integers(2, 8)); n = max(n, k + 2)
    maxp = float(rng.choice([1.0 / k + 0.02, 0.52, 0.6]))
    nk_len = int(rng.choice([1, 2, 3]))
    pred = sphere_box(rng, 300, (-10, 40), (30, 65))
    cen = sphere_box(rng, max(2, n // 15)); s = cen[rng.integers(0, len(cen), n)] + rng.normal(0, 0.2, (n, 2))
    try:
        kn.knndm_folds(s, pred, k, maxp, "hierarchical", 1, earth_radius_km=R, nk_len=nk_len); e1 = None
    except RuntimeError as e:
        e1 = "port"
    try:
        rcast.knndm_geo(s, pred, k, maxp, nk_len, R=R, rand=kn.random_folds(n, k, 1) + 1); e2 = None
    except RuntimeError as e:
        e2 = "r"
    nerr += e1 is not None or e2 is not None
    agree += (e1 is None) == (e2 is None)
print("error-case agreement:", agree, "of 200; cases with an error:", nerr)
