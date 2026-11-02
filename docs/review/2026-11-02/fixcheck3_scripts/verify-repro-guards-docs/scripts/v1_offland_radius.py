"""Claim 1/8: is nearest_country None in results/site_diagnostics.json caused by the 5-degree literal
(site_diagnostics.py:111)? Reads data/raw Natural Earth (run with python -I -B). Nothing is written."""
import sys

sys.path.insert(0, "/home/user/MSHI")

import geopandas as gpd  # noqa: E402

from mshi.config import load_config  # noqa: E402
from mshi.data.fetch import naturalearth_path  # noqa: E402
from mshi.netutil import verify_sha256  # noqa: E402

cfg = load_config()
f = "ne_50m_admin_0_countries.geojson"
p = naturalearth_path(cfg, f)
verify_sha256(p, cfg["sources"]["naturalearth"]["files"][f])
cty = gpd.read_file(p)[["ADMIN", "geometry"]]
for rec, lat, lon in [("srdb_793", 32.0, 135.42), ("srdb_1528", 53.05, 3.47),
                      ("srdb_11103", -42.15, -147.133), ("srdb_13828", 1.315, 193.911)]:
    pt = gpd.points_from_xy([lon], [lat])[0]
    d = sorted((g.distance(pt), a) for a, g in zip(cty.ADMIN, cty.geometry))[:3]
    print(rec, lat, lon, "nearest planar-degree distances:", [(a, round(x, 2)) for x, a in d],
          "-> within the 5-degree literal:", d[0][0] < 5)
