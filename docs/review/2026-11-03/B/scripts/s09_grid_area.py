"""grid.cell_area_km2: the cells of a full 0.5-degree lon/lat grid sum to 4 pi R^2; a 1-degree equatorial cell is
(pi R / 180)^2 (to first order); the stand-in grid has no Russian cell east of the antimeridian labelled Europe."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.analysis.grid import cell_area_km2
R = 6371.0
deg = 0.5
lat = np.arange(-90 + deg / 2, 90, deg)
tot = cell_area_km2(lat, deg, R).sum() * (360 / deg)
print("sum of 0.5-deg cell areas / (4 pi R^2) =", tot / (4 * np.pi * R ** 2))
print("1-deg cell at the equator:", cell_area_km2(np.array([0.5]), 1.0, R)[0], "vs (pi R/180)^2 =", (np.pi * R / 180) ** 2)
g = pd.read_parquet("ne_grid_0p5.parquet")
print("Russian cells with lon<0 labelled:", g[(g.subunit == "Russia") & (g.lon < 0)].continent_geo.value_counts().to_dict())
