"""Cost of geographic_continent's off-coast loop in climate_grid: 0.5-degree cell centres outside every Natural Earth
subunit but within 0.5 degree of land (an upper bound on the cells WorldClim's land mask can add there); time per
nearest_within_km call on a random sample of 60 of them."""
import sys, time
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd, geopandas as gpd
from mshi.config import load_config
from mshi.geo import subunits, nearest_within_km
cfg = load_config(); su = subunits(cfg)
g = pd.read_parquet("ne_grid_0p5.parquet")
land = set(zip(g.lon.round(2), g.lat.round(2)))
cand = set()
for lo, la in land:
    for dx in (-0.5, 0, 0.5):
        for dy in (-0.5, 0, 0.5):
            p = (round(lo + dx, 2), round(la + dy, 2))
            if p not in land and -180 < p[0] < 180 and -90 < p[1] < 90:
                cand.add(p)
cand = np.array(sorted(cand))
print("offshore cell centres adjacent to land cells:", len(cand))
rng = np.random.default_rng(0)
smp = cand[rng.choice(len(cand), 60, replace=False)]
t0 = time.time(); hits = 0
for lo, la in smp:
    k, km = nearest_within_km(lo, la, su.geometry, cfg["site_build"]["continent"]["nearest_max_m"] / 1000)
    hits += k is not None
dt = (time.time() - t0) / len(smp)
print(f"{dt*1000:.0f} ms per call; {hits}/60 matched within 50 km; if all {len(cand)} were WorldClim land: ~{dt*len(cand)/60:.0f} min")
