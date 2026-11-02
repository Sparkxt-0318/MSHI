import sys, numpy as np, pandas as pd, geopandas as gpd
V = sys.argv[1]
NE = "/home/user/MSHI/data/raw/naturalearth/v5.1.2"
cty = gpd.read_file(f"{NE}/ne_50m_admin_0_countries.geojson")
print(cty[cty.ADMIN.isin(["France","Spain","Portugal","Norway","United States of America","Netherlands","Denmark","United Kingdom"])][["ADMIN","CONTINENT"]].to_string())
srdb = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
for tag in ["qc", "repo"]:
    st = pd.read_parquet(f"{V}/out/v3/sites_v3_{tag}.parquet")
    eu = st[st.continent == "Europe"]
    box = eu.lon.between(-32, 70) & eu.lat.between(34, 82)
    print(f"\n[{tag}] Europe sites: {len(eu)}; outside sanity box lon -32..70, lat 34..82: {(~box).sum()}")
    print(eu[~box][["site_id","lat","lon","log_rs","n_rec","n_cosore","country","ecosystem"]].to_string())
    print(f"[{tag}] Europe mean log_rs {eu.log_rs.mean():.3f} SD(ddof0) {eu.log_rs.std(ddof=0):.4f}  max log_rs {eu.log_rs.max():.3f}; rank of out-of-box log_rs among Europe:",
          [int((eu.log_rs > v).sum())+1 for v in eu[~box].log_rs])
    na = st[st.continent == "North America"]
    s24 = na[na.lat < 24]
    print(f"[{tag}] NA sites: {len(na)}; south of 24N: {len(s24)}; of which Hawaii (lon < -150): {(s24.lon < -150).sum()}; by country:", s24.country.value_counts().to_dict())
# which SRDB rows/sites are those?
st = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
qcr = rec  # match records to out-of-box Europe sites by proximity
eu = st[(st.continent=="Europe") & ~(st.lon.between(-32,70) & st.lat.between(34,82))]
for _, s in eu.iterrows():
    m = rec[(np.hypot(rec.lat - s.lat, rec.lon - s.lon) < 0.06)]
    for _, r in m.iterrows():
        idx = int(r.rec_id.split("_")[1]) if r.rec_id.startswith("srdb_") else None
        extra = srdb.loc[idx, ["Site_name","Region","Country","Ecosystem_type","MAT","MAP","Rs_annual","Study_number"]].to_dict() if idx is not None else {}
        print(s.site_id, r.rec_id, r.lat, r.lon, round(r.rs,1), r.geo_country, r.continent, "flags:", [f for f in ["f_method","f_quality","f_coverage","f_ecosys","f_dup","f_coord","f_offland"] if r[f]], extra)
