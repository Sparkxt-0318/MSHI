import sys, numpy as np, pandas as pd, geopandas as gpd
G, NE = sys.argv[1:3]
g = pd.read_parquet(G)
# N2c footprint (exp_poststrat.py: exclude 11,13,15,17; keep 16 as Desert; n>=20 over mapped classes)
inc = [f"n{k}" for k in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16)]
g["n_c"] = g[inc].sum(axis=1); g = g[g.n_c >= 20].copy()
g["w"] = np.cos(np.radians(g.lat)) * g.n_c   # proportional to included area
pts = gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.lon, g.lat), crs=4326)
cty = gpd.read_file(NE + "/ne_50m_admin_0_countries.geojson")[["ADMIN", "CONTINENT", "geometry"]]
j = gpd.sjoin(pts, cty, how="left", predicate="within"); j = j[~j.index.duplicated()]
j.loc[(j.ADMIN == "Russia"), "CONTINENT"] = np.where(j.loc[(j.ADMIN == "Russia"), "lon"] >= 60, "Asia", "Europe")
j["CONTINENT"] = j.CONTINENT.fillna("(centre off-polygon)")
w = j.w / j.w.sum()
print("N2c footprint area share by Natural Earth continent of cell centre:")
print(w.groupby(j.CONTINENT).sum().round(3).sort_values(ascending=False).to_string())
# woody savanna (8) and savanna (9) area by latitude band and continent
for code in (8, 9, 16):
    a = j[f"n{code}"] * np.cos(np.radians(j.lat)); a = a / a.sum()
    band = pd.cut(j.lat, [-10, 23.5, 40, 50, 60, 80])
    print(f"\nIGBP {code} area share by latitude band:", a.groupby(band, observed=True).sum().round(3).to_dict())
    print(f"IGBP {code} area share by continent:", a.groupby(j.CONTINENT).sum().round(3).sort_values(ascending=False).head(5).to_dict())
