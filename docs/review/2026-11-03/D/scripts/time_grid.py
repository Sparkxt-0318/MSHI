"""Time climate_grid's two parts (raster sampling; geographic_continent) on the sandbox's synthetic WorldClim,
and count the cells whose centre lies outside every Natural Earth map subunit (the per-point nearest-subunit loop)."""
import sys, time
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from mshi.config import load_config
from mshi.data.features import sample_raster
from mshi.data.rasters import worldclim_path
from mshi.geo import subunits, nearest_within_km
cfg = load_config(Path(sys.argv[1]))
deg = 0.5
lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
t = time.time()
for i in range(1, 20):
    v = sample_raster(worldclim_path(cfg, i), g.lon.values, g.lat.values)
    g[f"bio{i:02d}"] = np.where(v < -1e30, np.nan, v)
g = g.dropna().reset_index(drop=True)
print(f"sampling 19 layers at {lon.size} centres: {time.time() - t:.1f}s; land cells {len(g)}")
su = subunits(cfg)
t = time.time()
pts = gpd.GeoDataFrame({"i": np.arange(len(g))}, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326)
j = gpd.sjoin(pts, su, how="left", predicate="within")
j = j[~j.index.duplicated()].sort_values("i")
off = np.flatnonzero(j.SUBUNIT.isna().values)
print(f"sjoin: {time.time() - t:.1f}s; cells outside every subunit: {len(off)}")
t = time.time()
n = min(200, len(off))
for i in off[:n]:
    nearest_within_km(g.lon.values[i], g.lat.values[i], su.geometry, 50.0)
dt = (time.time() - t) / max(n, 1)
print(f"nearest_within_km: {dt * 1000:.1f} ms per off-coast cell -> about {dt * len(off):.0f}s for all {len(off)}")
