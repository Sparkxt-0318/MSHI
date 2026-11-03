"""The real mshi.analysis.grid.climate_grid on synthetic WorldClim stand-ins: 19 global GeoTIFFs (0.25 degree,
float32, nodata -3.4e38 over the ocean; land = Natural Earth 1:50m land rasterized with all_touched, so the mask is
more generous than the 1:50m subunits, as WorldClim's is), recorded as the outputs of a sandbox fetch_worldclim
result. Checks: cells kept, continent labels (incl. the off-coast nearest-subunit loop), area, run time, and
prediction_domain on the result."""
import sys, time, copy, json
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from mshi.config import load_config, Config
from mshi.io import write_result
from mshi.data.rasters import worldclim_path
from mshi.data.fetch import naturalearth_path
from mshi.analysis.grid import climate_grid
from mshi.analysis import transfer as T
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
base = load_config()
data = copy.deepcopy(base.data)
data["paths"]["raw"] = str(OUT / "raw")
cfg = Config(data, source=base.source, out_root=OUT / "out")
# Natural Earth files are pinned sources read from paths.raw: link the verified local copies into the sandbox raw dir
src_ne = naturalearth_path(base, "ne_50m_admin_0_map_subunits.geojson")
dst_ne = naturalearth_path(cfg, "ne_50m_admin_0_map_subunits.geojson")
dst_ne.parent.mkdir(parents=True, exist_ok=True)
for f in ("ne_50m_admin_0_map_subunits.geojson", "ne_50m_land.geojson"):
    d = naturalearth_path(cfg, f)
    if not d.exists():
        d.write_bytes(naturalearth_path(base, f).read_bytes())
land = gpd.read_file(naturalearth_path(cfg, "ne_50m_land.geojson"))
res = 0.25
W, H = int(360 / res), int(180 / res)
tr = from_origin(-180, 90, res, res)
mask = rasterize(((g, 1) for g in land.geometry), out_shape=(H, W), transform=tr, all_touched=True, fill=0).astype(bool)
lat = 90 - res / 2 - np.arange(H) * res
lon = -180 + res / 2 + np.arange(W) * res
LON, LAT = np.meshgrid(lon, lat)
paths = []
for i in range(1, 20):
    v = (30 - 0.5 * np.abs(LAT) + i * 0.1 + np.sin(np.radians(LON)) * i).astype("float32")
    v[~mask] = np.float32(-3.4e38)
    p = worldclim_path(cfg, i); p.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(p, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32", crs="EPSG:4326",
                       transform=tr, nodata=-3.4e38, tiled=True, compress="deflate") as dst:
        dst.write(v, 1)
    paths.append(p)
write_result(cfg, {"synthetic": True}, "fetch_worldclim.json", outputs=paths)
t0 = time.time()
g = climate_grid(cfg, 0.5)
dt = time.time() - t0
print(f"climate_grid: {len(g)} cells in {dt:.0f}s; NaN in bio: {int(g.filter(like='bio').isna().sum().sum())}; "
      f"continent_geo None: {int(g.continent_geo.isna().sum())}")
print("area (million km2) by continent_geo:", (g.groupby("continent_geo").area_km2.sum() / 1e6).round(2).to_dict())
K = cfg["phase2"]["within"]["knndm"]
for c in ("Asia", "Europe", "North America"):
    dom = T.prediction_domain(g, c, K)
    print(c, "prediction points:", dom.shape, "unique cells drawn:", len(np.unique(dom, axis=0)))
