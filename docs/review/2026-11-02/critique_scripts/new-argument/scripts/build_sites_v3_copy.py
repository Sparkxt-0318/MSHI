"""v3 site table: SRDB v5 + COSORE v0.8.0, record-level QC flags, coordinate/country check,
records merged into sites (5 km connected components), continent assignment.

Usage: python build_sites_v3.py SRDB_CSV COSORE_CSV NE_DIR OUT_DIR
Outputs: records_v3.parquet (all records + flags), sites_v3_qc.parquet (primary: QC filters on),
         sites_v3_repo.parquet (repo filters only, for sensitivity), build_summary.json
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree

SRDB, COS, NE, OUT = map(Path, sys.argv[1:5]); OUT.mkdir(parents=True, exist_ok=True)
S = {}
s = pd.read_csv(SRDB, low_memory=False)
s = s.rename(columns={"Latitude": "lat", "Longitude": "lon", "Rs_annual": "rs"})
s["src"] = "srdb"; s["rec_id"] = "srdb_" + s.index.astype(str)
s = s.dropna(subset=["lat", "lon", "rs"])
s = s[(s.rs >= 50) & (s.rs <= 4500)]
s = s[s.Manipulation.isin(["None", "Control", "control"]) | s.Manipulation.isna()].copy()
S["srdb_repo_filter_records"] = len(s)

# QC flags (a priori; see prep_log decision D7)
s["f_method"] = s.Meas_method.fillna("").str.contains("alkali|soda", case=False)
s["f_quality"] = s.Quality_flag.fillna("").str.contains(r"Q1[0-4]", regex=True)
s["f_coverage"] = s.Annual_coverage.notna() & (s.Annual_coverage < 0.5)
s["f_ecosys"] = s.Ecosystem_type.isin(["Wetland", "Urban"])
s["f_dup"] = s.Duplicate_record.notna()

c = pd.read_csv(COS)
c = c.rename(columns={"latitude": "lat", "longitude": "lon", "rs_annual": "rs"})
c = c[(c.rs >= 50) & (c.rs <= 4500)].copy()
c["src"] = "cosore"; c["rec_id"] = c.site_id
c["Country"] = np.nan; c["Ecosystem_type"] = c.get("igbp"); c["Study_midyear"] = np.nan
for f in ["f_method", "f_quality", "f_coverage", "f_ecosys", "f_dup"]: c[f] = False
c["f_ecosys"] = c["Ecosystem_type"].astype(str).str.upper().isin(["WET", "WETLAND", "URB"])
keep = ["rec_id", "src", "lat", "lon", "rs", "Country", "Ecosystem_type", "Ecosystem_state", "Study_midyear",
        "Meas_method", "Quality_flag", "Annual_coverage", "f_method", "f_quality", "f_coverage", "f_ecosys", "f_dup"]
r = pd.concat([s.reindex(columns=keep), c.reindex(columns=keep)], ignore_index=True)

# Country / continent by point-in-polygon (nearest within 50 km for coastal points)
cty = gpd.read_file(NE / "ne_50m_admin_0_countries.geojson")[["ADMIN", "NAME", "CONTINENT", "geometry"]]
g = gpd.GeoDataFrame(r, geometry=gpd.points_from_xy(r.lon, r.lat), crs=4326)
j = gpd.sjoin(g, cty, how="left", predicate="within"); j = j[~j.index.duplicated()]
miss = j.ADMIN.isna()
if miss.any():
    nn = gpd.sjoin_nearest(g[miss].to_crs(3857), cty.to_crs(3857), how="left", max_distance=50000)
    nn = nn[~nn.index.duplicated()]
    j.loc[nn.index, ["ADMIN", "NAME", "CONTINENT"]] = nn[["ADMIN", "NAME", "CONTINENT"]].values
r["geo_country"], r["continent"] = j.ADMIN.values, j.CONTINENT.values
# Russia: split at 60E (Urals)
rus = r.geo_country.eq("Russia")
r.loc[rus, "continent"] = np.where(r.loc[rus, "lon"] >= 60, "Asia", "Europe")

# coordinate check: SRDB reported country vs polygon country (normalised)
alias = {"USA": "United States of America", "United States": "United States of America", "US": "United States of America",
         "Florida": "United States of America", "Alaska": "United States of America", "Korea": "South Korea",
         "South Korea": "South Korea", "Republic of Korea": "South Korea", "UK": "United Kingdom", "England": "United Kingdom",
         "Scotland": "United Kingdom", "Wales": "United Kingdom", "Malyasia": "Malaysia", "Isreal": "Israel",
         "Czech Republic": "Czechia", "Democratic Republic of Congo": "Democratic Republic of the Congo",
         "Congo": "Republic of the Congo", "Tanzania": "United Republic of Tanzania", "Serbia": "Republic of Serbia",
         "Taiwan": "Taiwan", "Puerto Rico": "Puerto Rico", "Hong Kong": "Hong Kong S.A.R."}
rep = r.Country.astype(str).str.strip().map(lambda x: alias.get(x, x))
mism = (r.src == "srdb") & r.Country.notna() & r.geo_country.notna() & (rep != r.geo_country)
# a mismatch is only a coordinate error if the point lies > 100 km from the reported country's polygon
cty_m = cty.to_crs(3857).set_index("ADMIN").geometry
pts_m = gpd.GeoSeries(gpd.points_from_xy(r.lon, r.lat), crs=4326).to_crs(3857)
dist = np.full(len(r), np.nan)
for i in np.where(mism)[0]:
    name = rep.iat[i]
    if name in cty_m.index:
        dist[i] = pts_m.iat[i].distance(cty_m.loc[name] if not isinstance(cty_m.loc[name], gpd.GeoSeries) else cty_m.loc[name].iloc[0]) / 1000
r["dist_to_reported_country_km"] = dist
terr = {("United States of America", "Puerto Rico"), ("Denmark", "Greenland"), ("France", "New Caledonia"), ("Denmark", "Norway")}
is_terr = pd.Series([(a, b) in terr for a, b in zip(rep, r.geo_country)], index=r.index)
r["f_coord"] = mism & (r.dist_to_reported_country_km > 100) & ~is_terr
r["f_offland"] = r.continent.isna()
S["coord_mismatch_records"] = int(r.f_coord.sum())
S["coord_mismatch_examples"] = r[r.f_coord][["Country", "geo_country", "lat", "lon", "dist_to_reported_country_km"]].drop_duplicates().head(40).astype(str).values.tolist()

r["log_rs"] = np.log(r.rs)
r.to_parquet(OUT / "records_v3.parquet", index=False)


def to_sites(rr, tag):
    X = np.radians(rr[["lat", "lon"]].values)
    tree = BallTree(X, metric="haversine")
    nb = tree.query_radius(X, r=5.0 / 6371.0)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    from scipy.sparse import coo_matrix
    A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr), len(rr)))
    _, lab = connected_components(A, directed=False)
    rr = rr.assign(site=lab)
    agg = rr.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"),
                                 log_rs_sd=("log_rs", "std"), n_rec=("log_rs", "size"),
                                 n_cosore=("src", lambda x: int((x == "cosore").sum())),
                                 ecosystem=("Ecosystem_type", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
                                 ecosys_state=("Ecosystem_state", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
                                 year_med=("Study_midyear", "median"), continent=("continent", lambda x: x.mode().iat[0]),
                                 country=("geo_country", lambda x: x.mode().iat[0]))
    agg["site_id"] = [f"v3{tag}_{i:05d}" for i in agg.index]
    agg["rs"] = np.exp(agg.log_rs)
    return agg.reset_index(drop=True)


base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)]
S["records_after_coord_check"] = len(base); S["records_after_qc"] = len(qc)
S["qc_removed_by"] = {f: int(base[f].sum()) for f in ["f_method", "f_quality", "f_coverage", "f_ecosys", "f_dup"]}
for name, rr in [("qc", qc), ("repo", base)]:
    st = to_sites(rr.reset_index(drop=True), name)
    st.to_parquet(OUT / f"sites_v3_{name}.parquet", index=False)
    S[f"sites_{name}"] = {"n": len(st), "by_continent": st.continent.value_counts().to_dict(),
                          "sites_with_2plus_records": int((st.n_rec >= 2).sum())}
(OUT / "build_summary.json").write_text(json.dumps(S, indent=1, default=str))
print(json.dumps(S, indent=1, default=str))
