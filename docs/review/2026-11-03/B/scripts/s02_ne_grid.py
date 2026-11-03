"""A synthetic stand-in for mshi.analysis.grid.climate_grid: 0.5-degree cells whose centre lies inside a Natural
Earth 1:50m map subunit (instead of the WorldClim land mask, which cannot be downloaded here), labelled with
mshi.geo.geographic_continent (the same rule as climate_grid) and the exact cell area (grid.cell_area_km2).
Saved to work/ne_grid_0p5.parquet for later checks. Reports each continent's area and the Greenland share."""
import sys, time
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd, geopandas as gpd
from mshi.config import load_config
from mshi.geo import subunits, geographic_continent
from mshi.analysis.grid import cell_area_km2
cfg = load_config()
t0 = time.time()
su = subunits(cfg)
deg = 0.5
lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
pts = gpd.GeoDataFrame({"i": np.arange(len(g))}, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326)
j = gpd.sjoin(pts, su[["geometry"]], how="inner", predicate="within")
inside = np.unique(j.i.values)
g = g.iloc[inside].reset_index(drop=True)
c = geographic_continent(cfg, g.lon.values, g.lat.values, su)
g["continent_geo"] = c.continent_geo.values
g["subunit"] = c.geo_subunit.values
g["area_km2"] = cell_area_km2(g.lat.values, deg, cfg["site_build"]["earth_radius_km"])
g.to_parquet("ne_grid_0p5.parquet", index=False)
print(f"{len(g)} land cells, {time.time()-t0:.0f}s")
a = g.groupby("continent_geo").area_km2.sum() / 1e6
print("area (million km2) by continent_geo:\n", a.round(2))
na = g[g.continent_geo == "North America"]
gr = na.subunit.eq("Greenland")
print("North America: Greenland share of area = %.3f (cells %d of %d)" % (na.area_km2[gr].sum() / na.area_km2.sum(), gr.sum(), len(na)))
eu = g[g.continent_geo == "Europe"]
print("Europe subunits with the largest area:", (eu.groupby('subunit').area_km2.sum()/1e6).sort_values(ascending=False).head(6).round(2).to_dict())
