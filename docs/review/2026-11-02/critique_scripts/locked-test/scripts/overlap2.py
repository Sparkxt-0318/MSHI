import sys, json
import numpy as np, pandas as pd, geopandas as gpd
from sklearn.neighbors import BallTree
W, V2, NE = sys.argv[1:4]
v2 = pd.read_parquet(V2)
s = pd.read_parquet(f"{W}/out/v3/sites_v3_qc.parquet")
eu = s[s.continent == "Europe"].reset_index(drop=True)
t = BallTree(np.radians(eu[["lat", "lon"]].values), metric="haversine")
d, _ = t.query(np.radians(v2[["latitude", "longitude"]].values), k=1)
v2["near_eu"] = d[:, 0] * 6371 <= 5
BIO = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
MOD = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
F = v2.dropna(subset=["log_rs_annual"] + BIO); FN = v2.dropna(subset=["log_rs_annual"] + BIO + MOD)
print("v2 sites near a v3 Europe QC test site:", int(v2.near_eu.sum()), "| in F rows (n=%d):" % len(F), int(F.near_eu.sum()),
      "| in F+NPP rows (n=%d):" % len(FN), int(FN.near_eu.sum()))
print("their source:", v2[v2.near_eu].source.value_counts().to_dict())
# coastal / off-polygon sites (candidates for WorldClim NaN)
cty = gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")[["ADMIN", "geometry"]]
for cont in ["Asia", "Europe"]:
    x = s[s.continent == cont]
    g = gpd.GeoDataFrame(x, geometry=gpd.points_from_xy(x.lon, x.lat), crs=4326)
    j = gpd.sjoin(g, cty, how="left", predicate="within"); j = j[~j.index.duplicated()]
    off = j[j.ADMIN.isna()]
    print(cont, "QC sites not inside any NE-50m country polygon:", len(off))
    print(off[["site_id", "lat", "lon", "country", "log_rs", "n_rec"]].to_string())
