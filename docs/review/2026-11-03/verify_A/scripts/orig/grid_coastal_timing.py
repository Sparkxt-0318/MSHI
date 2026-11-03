"""How many 0.5-deg cell centres lie outside every Natural Earth subunit but within 10 km of one (the cells a
WorldClim land mask may keep while geographic_continent needs its nearest-subunit search), and how long that search
takes per cell."""
import sys, time
import numpy as np, geopandas as gpd
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.geo import subunits, geographic_continent
cfg = load_config()
su = subunits(cfg)
deg = 0.5
lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
g = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon.ravel(), lat.ravel()), crs=4326)
inside = gpd.sjoin(g, su, how="inner", predicate="within").index.unique()
out = g.drop(index=inside)
land = su.union_all() if hasattr(su, "union_all") else su.unary_union
near = out[out.distance(land) < 0.1]          # within ~0.1 deg (lon/lat units) of land
print("cells inside subunits:", len(inside), "; outside but within 0.1 deg of land:", len(near))
rng = np.random.default_rng(0)
s = near.sample(min(300, len(near)), random_state=1)
t = time.time()
r = geographic_continent(cfg, s.geometry.x.values, s.geometry.y.values, su)
dt = time.time() - t
print("nearest-subunit search: %d cells in %.1f s (%.3f s per cell); matched within 50 km: %d" %
      (len(s), dt, dt / len(s), r.continent_geo.notna().sum()))
print("estimated time for all %d such cells: %.0f s" % (len(near), dt / len(s) * len(near)))
