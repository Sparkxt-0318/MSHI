"""Recompute the coordinate-check distance (point -> reported-country polygon) geodesically, via a local azimuthal
equidistant projection centred on each point (country geometry clipped to +/-20 deg around the point first)."""
import sys, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import box, Point
V = sys.argv[1]; NE = "/home/user/MSHI/data/raw/naturalearth/v5.1.2"
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
srdb = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
cty = gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")[["ADMIN", "geometry"]].set_index("ADMIN")
alias = {"USA": "United States of America", "United States": "United States of America", "US": "United States of America",
         "Florida": "United States of America", "Alaska": "United States of America", "Korea": "South Korea",
         "South Korea": "South Korea", "Republic of Korea": "South Korea", "UK": "United Kingdom", "England": "United Kingdom",
         "Scotland": "United Kingdom", "Wales": "United Kingdom", "Malyasia": "Malaysia", "Isreal": "Israel",
         "Czech Republic": "Czechia", "Democratic Republic of Congo": "Democratic Republic of the Congo",
         "Congo": "Republic of the Congo", "Tanzania": "United Republic of Tanzania", "Serbia": "Republic of Serbia",
         "Taiwan": "Taiwan", "Puerto Rico": "Puerto Rico", "Hong Kong": "Hong Kong S.A.R."}
rep = rec.Country.astype(str).str.strip().map(lambda x: alias.get(x, x))
mism = (rec.src == "srdb") & rec.Country.notna() & rec.geo_country.notna() & (rep != rec.geo_country)
terr = {("United States of America", "Puerto Rico"), ("Denmark", "Greenland"), ("France", "New Caledonia"), ("Denmark", "Norway")}
rows = []
for i in np.where(mism)[0]:
    r = rec.iloc[i]; name = rep.iat[i]
    if name not in cty.index: continue
    g = cty.loc[name, "geometry"]
    win = box(r.lon - 20, r.lat - 20, r.lon + 20, r.lat + 20); gc = g.intersection(win)
    if gc.is_empty: dg = np.inf
    else:
        aeqd = f"+proj=aeqd +lat_0={r.lat} +lon_0={r.lon} +datum=WGS84 +units=m"
        gp = gpd.GeoSeries([gc], crs=4326).to_crs(aeqd).iloc[0]
        dg = gp.distance(Point(0, 0)) / 1000
    rows.append(dict(rec_id=r.rec_id, Country=r.Country, rep=name, geo=r.geo_country, lat=r.lat, lon=r.lon, d_merc=r.dist_to_reported_country_km,
                     d_geo=dg, terr=(name, r.geo_country) in terr, f_coord=bool(r.f_coord)))
d = pd.DataFrame(rows)
d["row"] = d.rec_id.str.replace("srdb_", "").astype(int)
d = d.join(srdb[["Site_name", "Region"]], on="row")
d["ratio"] = d.d_merc / d.d_geo
print("checkable mismatches:", len(d), " flagged as handoff (Mercator):", int(d.f_coord.sum()),
      " flagged with geodesic >100 km (non-territory):", int(((d.d_geo > 100) & ~d.terr).sum()))
print("Mercator/geodesic ratio vs sec(lat) (records 20-2000 km):")
q = d[(d.d_geo > 20) & (d.d_geo < 2000)]; print((q.ratio / (1 / np.cos(np.radians(q.lat)))).describe()[["count", "mean", "min", "max"]].round(3).to_dict())
flip = d[d.f_coord & ~(d.d_geo > 100)]
print("\nflagged under Mercator but <=100 km geodesic:", len(flip)); print(flip[["Country", "geo", "lat", "lon", "d_merc", "d_geo", "Site_name", "Region"]].round(1).to_string(index=False))
flip2 = d[~d.f_coord & (d.d_geo > 100) & ~d.terr]
print("\nflagged geodesic but not Mercator:", len(flip2))
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 45)
print("\nall 52 flagged records grouped:")
f = d[d.f_coord]
print(f.groupby(["Country", "geo"]).agg(n=("rec_id", "size"), lat=("lat", "first"), lon=("lon", "first"), d_geo=("d_geo", "min"),
      site=("Site_name", lambda x: "; ".join(sorted(set(map(str, x))))[:45]), region=("Region", lambda x: "; ".join(sorted(set(map(str, x))))[:40])).round(1).to_string())
d.to_csv(f"{V}/out/coord_geodesic.csv", index=False)
