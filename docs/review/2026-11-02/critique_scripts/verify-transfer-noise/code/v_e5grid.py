import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.windows import Window
NE = "/home/user/MSHI/data/raw/naturalearth/v5.1.2/"
lon, lat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-59.75, 84, 0.5))   # exp_global_aoa.py:18
g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
g["area_km2"] = (111.32 * 0.5) ** 2 * np.cos(np.radians(g.lat))                     # exp_global_aoa.py:25
pts = gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326)
cty = gpd.read_file(NE + "ne_50m_admin_0_countries.geojson")[["ADMIN", "geometry"]]
j = gpd.sjoin(pts, cty, how="inner", predicate="within"); j = j[~j.index.duplicated()]
land = g.loc[j.index].assign(admin=j.ADMIN.values)
land = land[land.admin != "Antarctica"]
arc = land.lat > 66.5
print("cells:", len(g), "NE-50m land cells (excl Antarctica):", len(land), "lat range", land.lat.min(), land.lat.max())
gl = land.admin.eq("Greenland")
print("Greenland share of grid land area: %.4f" % (land.area_km2[gl].sum() / land.area_km2.sum()))
print("Greenland share of Arctic band (66.5,84] land area: %.4f" % (land.area_km2[gl & arc].sum() / land.area_km2[arc].sum()))
print("Greenland land area in grid (M km2): %.2f" % (land.area_km2[gl].sum() / 1e6))
print("Arctic band share of total land area: %.4f" % (land.area_km2[arc].sum() / land.area_km2.sum()))
# same with the 1:50m land polygons
lp = gpd.read_file(NE + "ne_50m_land.geojson")[["geometry"]]
j2 = gpd.sjoin(pts, lp, how="inner", predicate="within"); j2 = j2[~j2.index.duplicated()]
print("NE-50m land-polygon cells:", j2.index.nunique())
# IGBP barren / snow share in the MODIS footprint
with rasterio.open("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/modis/landcover_igbp_2023.tif") as s:
    print("IGBP raster:", s.width, s.height, s.res, s.bounds, s.dtypes, "nodata", s.nodata)
    a = s.read(1); T = s.transform
rows = np.arange(a.shape[0]); latc = T.f + T.e * (rows + 0.5)
w = np.cos(np.radians(latc))[:, None] * np.ones((1, a.shape[1]))
vals, _ = np.unique(a, return_counts=True); print("classes present:", vals.tolist())
landm = (a >= 1) & (a <= 16)
for k, nm in [(16, "barren"), (15, "snow/ice")]:
    print(f"IGBP class {k} ({nm}) area share of land (classes 1-16): {(w * (a == k)).sum() / (w * landm).sum():.4f}")
print("water share (17) of non-zero cells:", round(float((w * (a == 17)).sum() / (w * (a > 0)).sum()), 4))
# does bio05 > -50 (line 26) drop anything plausible? Greenland ice sheet summit warmest-month max ~ -10 to -5 C (WorldClim not available; physical bound)
