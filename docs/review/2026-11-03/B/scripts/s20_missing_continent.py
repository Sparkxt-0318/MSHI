"""prediction_domain on a grid whose continent_geo has missing values (cells > 50 km from any subunit), built exactly as
climate_grid builds the column (geographic_continent(...).continent_geo.values)."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import load_config
from mshi.geo import geographic_continent, subunits
from mshi.analysis import transfer as T
from mshi.analysis.grid import cell_area_km2
cfg = load_config()
lon = np.array([10.25, 100.25, -100.25, -30.25, 160.25, 2.25])
lat = np.array([50.25, 40.25, 40.25, 0.25, -50.25, 48.75])
g = pd.DataFrame({"lon": lon, "lat": lat})
c = geographic_continent(cfg, lon, lat, subunits(cfg))
g["continent_geo"] = c.continent_geo.values
g["area_km2"] = cell_area_km2(lat, 0.5, 6371.0)
print("dtype:", g.continent_geo.dtype, "values:", g.continent_geo.tolist())
K = {"max_pred_points": 10, "seed": 42, "grid_deg": 0.5, "pred_weight": "area"}
print("Europe domain:", T.prediction_domain(g, "Europe", K)[:3].tolist())
for dt in ("string", "object", "category"):
    h = g.astype({"continent_geo": dt})
    try:
        print(dt, "->", len(T.prediction_domain(h, "Europe", K)))
    except Exception as e:
        print(dt, "-> ERROR", type(e).__name__, e)
