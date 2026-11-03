"""D-P2-12 numbers: 0.5-deg cell centres inside Natural Earth subunits that moved (Russia east of the antimeridian;
South Georgia), and sites in the other-continent parts of transcontinental countries."""
import sys
import numpy as np, pandas as pd, geopandas as gpd
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.geo import subunits
cfg = load_config()
su = subunits(cfg)
deg = 0.5
lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
g = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon.ravel(), lat.ravel()), crs=4326)
j = gpd.sjoin(g, su, how="inner", predicate="within")
rus_e = j[(j.ADMIN == "Russia") & (j.geometry.x < 0)]
print("0.5-deg cell centres inside Russian subunits at lon < 0:", len(rus_e))
sg = j[j.SUBUNIT.isin(["South Georgia", "South Sandwich Islands"])]
print("cell centres in South Georgia / South Sandwich:", sg.SUBUNIT.value_counts().to_dict())
for tag in ("qc", "repo"):
    s = pd.read_parquet(f"/home/user/MSHI/data/derived/sites_analysis_{tag}.parquet")
    tr = s[s.country == "Turkey"]
    print(tag, "Turkey sites west of 29.1E (East Thrace):", tr[tr.lon < 29.1][["site_id", "lat", "lon", "n_rec", "continent_geo"]].values.tolist())
    kz = s[(s.country == "Kazakhstan") & (s.lon < 52)]
    print(tag, "Kazakhstan sites west of 52E:", kz[["site_id", "lat", "lon"]].values.tolist())
    eg = s[(s.country == "Egypt") & (s.lon > 32.3)]
    print(tag, "Egypt sites east of 32.3E (Sinai):", eg[["site_id", "lat", "lon"]].values.tolist())
    idn = s[(s.country == "Indonesia") & (s.lon > 130.5)]
    print(tag, "Indonesia sites east of 130.5E (western New Guinea and Moluccas):", idn[["site_id", "lat", "lon"]].values.tolist())
    for c in ("Georgia", "Azerbaijan", "Armenia"):
        x = s[s.country == c]
        print(tag, c, "sites:", x[["site_id", "lat", "lon", "continent_geo"]].values.tolist())
