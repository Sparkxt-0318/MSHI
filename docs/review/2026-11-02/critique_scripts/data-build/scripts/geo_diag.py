import sys, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point
V3, NE = sys.argv[1], sys.argv[2]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
r = pd.read_parquet(f"{V3}/records_v3.parquet")
qs = pd.read_parquet(f"{V3}/sites_v3_qc.parquet"); rs = pd.read_parquet(f"{V3}/sites_v3_repo.parquet")
cty = gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")
print("NE CONTINENT values:", cty.CONTINENT.value_counts().to_dict())
# Europe-continent records: which geo_country, and which lie outside a European bbox (lon -25..60, lat 34..72)
eu = r[r.continent == "Europe"]
out = eu[(eu.lon < -25) | (eu.lon > 70) | (eu.lat < 34)]
print("\nRecords with continent=Europe outside Europe bbox:"); print(out[["rec_id","src","Country","geo_country","lat","lon","Ecosystem_type","rs","f_coord","f_offland","f_method","f_quality","f_coverage","f_ecosys","f_dup"]].to_string())
for nm, st in [("qc", qs), ("repo", rs)]:
    e = st[st.continent == "Europe"]
    o = e[(e.lon < -25) | (e.lon > 70) | (e.lat < 34)]
    print(f"\n{nm}: Europe sites {len(e)}; outside Europe bbox: {len(o)}")
    print(o[["site_id","lat","lon","country","ecosystem","n_rec","rs","log_rs"]].to_string())
    print(f"  Europe site log_rs mean {e.log_rs.mean():.3f} sd {e.log_rs.std():.3f}; those outside: {o.log_rs.round(3).tolist()}")
# all continents x geo_country cross-check: countries whose NE continent differs from their geographic location
for nm, st in [("qc", qs)]:
    print(f"\n{nm} sites by continent x country (top per continent):")
    for c, g in st.groupby("continent"):
        print(" ", c, g.country.value_counts().head(25).to_dict())
