import sys, numpy as np, pandas as pd, geopandas as gpd
from shapely.ops import nearest_points
from pyproj import Geod, CRS, Transformer
V3, NE = sys.argv[1], sys.argv[2]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
r = pd.read_parquet(f"{V3}/records_v3.parquet")
cty = gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")[["ADMIN", "NAME", "CONTINENT", "geometry"]]
geod = Geod(ellps="WGS84")
alias = {"USA": "United States of America", "United States": "United States of America", "US": "United States of America",
         "Florida": "United States of America", "Alaska": "United States of America", "Korea": "South Korea",
         "South Korea": "South Korea", "Republic of Korea": "South Korea", "UK": "United Kingdom", "England": "United Kingdom",
         "Scotland": "United Kingdom", "Wales": "United Kingdom", "Malyasia": "Malaysia", "Isreal": "Israel",
         "Czech Republic": "Czechia", "Democratic Republic of Congo": "Democratic Republic of the Congo",
         "Congo": "Republic of the Congo", "Tanzania": "United Republic of Tanzania", "Serbia": "Republic of Serbia",
         "Taiwan": "Taiwan", "Puerto Rico": "Puerto Rico", "Hong Kong": "Hong Kong S.A.R."}
rep = r.Country.astype(str).str.strip().map(lambda x: alias.get(x, x))
admin = set(cty.ADMIN)
srdb = r.src == "srdb"
mism = srdb & r.Country.notna() & r.geo_country.notna() & (rep != r.geo_country)
# 1) reported names that are not NE ADMIN names -> never checkable
unk = srdb & r.Country.notna() & ~rep.isin(admin)
print("SRDB records whose reported Country (after alias) is not an NE ADMIN name (never checked):", int(unk.sum()))
print(pd.crosstab(r.loc[unk, "Country"], r.loc[unk, "geo_country"].fillna("<offland>")).stack().loc[lambda x: x > 0].to_string())
# 2) geodesic distance from point to reported country polygon (true km) vs EPSG:3857 distance used by the script
def geodesic_km(lon, lat, geom):
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    g = gpd.GeoSeries([geom], crs=4326).to_crs(aeqd).iloc[0]
    from shapely.geometry import Point
    return g.distance(Point(0, 0)) / 1000
cm = cty.set_index("ADMIN").geometry
rows = []
for i in np.where(mism & rep.isin(admin))[0]:
    x = r.iloc[i]
    rows.append(dict(rec=x.rec_id, Country=x.Country, geo=x.geo_country, lat=x.lat, lon=x.lon, d3857=x.dist_to_reported_country_km,
                     dgeo=geodesic_km(x.lon, x.lat, cm.loc[rep.iat[i]] if not isinstance(cm.loc[rep.iat[i]], gpd.GeoSeries) else cm.loc[rep.iat[i]].iloc[0]),
                     f_coord=x.f_coord))
d = pd.DataFrame(rows)
d["flag_geo"] = (d.dgeo > 100) & ~d.apply(lambda z: (alias.get(z.Country, z.Country), z.geo) in {("United States of America", "Puerto Rico"), ("Denmark", "Greenland"), ("France", "New Caledonia"), ("Denmark", "Norway")}, axis=1)
print("\nmismatched & checkable records:", len(d), " flagged by script (3857):", int(d.f_coord.sum()), " flagged with geodesic 100 km:", int(d.flag_geo.sum()))
flip = d[d.f_coord != d.flag_geo]
print("records whose decision flips under geodesic distance:"); print(flip.round(2).to_string())
print("\nall flagged records grouped by (reported, located):")
f = d[d.f_coord]
print(f.groupby(["Country", "geo"]).agg(n=("rec", "size"), lat=("lat", "first"), lon=("lon", "first"), d3857=("d3857", "first"), dgeo=("dgeo", "first")).round(1).to_string())
d.to_csv(f"{V3}/../coord_diag.csv", index=False)
