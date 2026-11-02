"""SRDB v5 + COSORE v0.8.0 -> QC-flagged records -> 5-km sites -> continents.

Port of ``docs/handoff/scripts/build_sites_v3.py``. The filters, their order and every threshold are
kept exactly (they come from ``configs/v3.yaml``). Additions that do not change any count:
extra SRDB metadata columns (raw coordinate strings, Study_number, Leaf_habit, Biome, Species, ...)
and per-record site ids for both variants, for later phases.

Outputs
  data/derived/records_v3.parquet      all records with flags (coordinate check, QC)
  data/derived/sites_v3_qc.parquet     primary: coordinate check + QC filters
  data/derived/sites_v3_repo.parquet   sensitivity: repo filters + coordinate check only
  results/build_sites.json             counts (same keys as the handoff build_summary.json)
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from ..config import Config
from ..io import read_table, write_result, write_table
from ..netutil import verify_sha256
from ..spatial import cluster_within_km
from .fetch import naturalearth_path, srdb_csv_path

log = logging.getLogger("mshi.sites")

QC_FLAGS = ["f_method", "f_quality", "f_coverage", "f_ecosys", "f_dup"]
KEEP = ["rec_id", "src", "lat", "lon", "rs", "Country", "Ecosystem_type", "Ecosystem_state", "Study_midyear",
        "Meas_method", "Quality_flag", "Annual_coverage"] + QC_FLAGS
# SRDB metadata carried along for later phases (not used by any Phase-1 filter or count)
EXTRA_SRDB = ["Study_number", "Author", "Site_ID", "Site_name", "Biome", "Leaf_habit", "Species",
              "Partition_method", "Elevation", "Stage", "Duplicate_record", "Manipulation"]


def load_srdb_records(cfg: Config) -> tuple[pd.DataFrame, dict]:
    sb = cfg["site_build"]
    path = srdb_csv_path(cfg)
    verify_sha256(path, cfg["sources"]["srdb"]["sha256"])       # pinned bytes only
    s = read_table(cfg, path, low_memory=False)
    raw_coords = read_table(cfg, path, usecols=["Latitude", "Longitude"], dtype=str, keep_default_na=False)
    n_rows = len(s)
    s = s.rename(columns={"Latitude": "lat", "Longitude": "lon", "Rs_annual": "rs"})
    s["src"] = "srdb"
    s["srdb_row"] = s.index.astype(int)                 # ORIGINAL csv row index (pitfall: not post-filter)
    s["rec_id"] = "srdb_" + s.index.astype(str)
    s["lat_str"] = raw_coords["Latitude"].str.strip().values
    s["lon_str"] = raw_coords["Longitude"].str.strip().values
    s = s.dropna(subset=["lat", "lon", "rs"])
    lo, hi = sb["rs_range"]
    s = s[(s.rs >= lo) & (s.rs <= hi)]
    s = s[s.Manipulation.isin(sb["manipulation_keep"]) | s.Manipulation.isna()].copy()
    q = sb["qc"]
    s["f_method"] = s.Meas_method.fillna("").str.contains(q["method_regex"], case=False, regex=True)
    s["f_quality"] = s.Quality_flag.fillna("").str.contains(q["quality_regex"], regex=True)
    s["f_coverage"] = s.Annual_coverage.notna() & (s.Annual_coverage < q["min_annual_coverage"])
    s["f_ecosys"] = s.Ecosystem_type.isin(q["ecosystem_exclude"])
    s["f_dup"] = s.Duplicate_record.notna()
    return s, {"srdb_rows": n_rows, "srdb_repo_filter_records": int(len(s))}


def load_cosore_records(cfg: Config) -> pd.DataFrame:
    sb = cfg["site_build"]
    c = read_table(cfg, cfg.path("derived", "cosore_annual.csv"))
    c = c.rename(columns={"latitude": "lat", "longitude": "lon", "rs_annual": "rs"})
    lo, hi = sb["rs_range"]
    c = c[(c.rs >= lo) & (c.rs <= hi)].copy()
    c["src"] = "cosore"
    c["rec_id"] = c.site_id
    c["Country"] = np.nan
    c["Ecosystem_type"] = c.get("igbp")
    c["Study_midyear"] = np.nan
    for f in QC_FLAGS:
        c[f] = False
    # as in the handoff: compares upper-cased IGBP strings against WET/WETLAND/URB
    c["f_ecosys"] = c["Ecosystem_type"].astype(str).str.upper().isin(sb["qc"]["cosore_ecosystem_exclude_upper"])
    return c


def assign_countries(cfg: Config, r: pd.DataFrame) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    sb = cfg["site_build"]
    ne_file = "ne_50m_admin_0_countries.geojson"
    verify_sha256(naturalearth_path(cfg, ne_file), cfg["sources"]["naturalearth"]["files"][ne_file])
    cty = gpd.read_file(naturalearth_path(cfg, ne_file))[["ADMIN", "NAME", "CONTINENT", "geometry"]]
    g = gpd.GeoDataFrame(r, geometry=gpd.points_from_xy(r.lon, r.lat), crs=4326)
    j = gpd.sjoin(g, cty, how="left", predicate="within")
    j = j[~j.index.duplicated()].reindex(r.index)
    miss = j.ADMIN.isna()
    if miss.any():
        crs = sb["continent"]["nearest_crs"]
        nn = gpd.sjoin_nearest(g[miss].to_crs(crs), cty.to_crs(crs), how="left",
                               max_distance=sb["continent"]["nearest_max_m"])
        nn = nn[~nn.index.duplicated()]
        j.loc[nn.index, ["ADMIN", "NAME", "CONTINENT"]] = nn[["ADMIN", "NAME", "CONTINENT"]].values
    r = r.copy()
    r["geo_country"] = j.ADMIN.values
    r["continent"] = j.CONTINENT.values
    rus = r.geo_country.eq("Russia")
    r.loc[rus, "continent"] = np.where(r.loc[rus, "lon"] >= sb["continent"]["russia_split_lon"], "Asia", "Europe")
    return r, cty


def coordinate_check(cfg: Config, r: pd.DataFrame, cty: gpd.GeoDataFrame) -> pd.DataFrame:
    cc = cfg["site_build"]["coord_check"]
    alias = cc["aliases"]
    rep = r.Country.astype(str).str.strip().map(lambda x: alias.get(x, x))
    mism = (r.src == "srdb") & r.Country.notna() & r.geo_country.notna() & (rep != r.geo_country)
    cty_m = cty.to_crs(cc["distance_crs"]).set_index("ADMIN").geometry
    pts_m = gpd.GeoSeries(gpd.points_from_xy(r.lon, r.lat), crs=4326).to_crs(cc["distance_crs"])
    dist = np.full(len(r), np.nan)
    unknown = []
    for i in np.where(mism.values)[0]:
        name = rep.iat[i]
        if name in cty_m.index:
            geom = cty_m.loc[name]
            geom = geom.iloc[0] if isinstance(geom, gpd.GeoSeries) else geom
            dist[i] = pts_m.iat[i].distance(geom) / 1000.0
        else:
            unknown.append(name)
    r = r.copy()
    r["reported_country_norm"] = rep.values
    r["dist_to_reported_country_km"] = dist
    terr = {tuple(t) for t in cc["territory_exceptions"]}
    is_terr = pd.Series([(a, b) in terr for a, b in zip(rep, r.geo_country)], index=r.index)
    r["f_coord"] = mism & (r.dist_to_reported_country_km > cc["max_km"]) & ~is_terr
    r["f_offland"] = r.continent.isna()
    r.attrs["coord_unknown_reported_names"] = sorted(set(map(str, unknown)))
    r.attrs["coord_mismatch_any"] = int(mism.sum())
    return r


def to_sites(cfg: Config, rr: pd.DataFrame, tag: str) -> tuple[pd.DataFrame, np.ndarray]:
    sb = cfg["site_build"]
    lab = cluster_within_km(rr.lat.values, rr.lon.values, sb["merge_radius_km"], sb["earth_radius_km"])
    rr = rr.assign(site=lab)
    agg = rr.groupby("site").agg(
        lat=("lat", "mean"), lon=("lon", "mean"), log_rs=("log_rs", "mean"),
        log_rs_sd=("log_rs", "std"), n_rec=("log_rs", "size"),
        n_cosore=("src", lambda x: int((x == "cosore").sum())),
        ecosystem=("Ecosystem_type", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
        ecosys_state=("Ecosystem_state", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
        year_med=("Study_midyear", "median"), continent=("continent", lambda x: x.mode().iat[0]),
        country=("geo_country", lambda x: x.mode().iat[0]))
    agg["site_id"] = [f"v3{tag}_{i:05d}" for i in agg.index]
    agg["rs"] = np.exp(agg.log_rs)
    site_of_record = np.array([f"v3{tag}_{i:05d}" for i in lab], dtype=object)
    return agg.reset_index(drop=True), site_of_record


def build_sites(cfg: Config) -> dict:
    S: dict = {}
    s, info = load_srdb_records(cfg)
    S.update(info)
    c = load_cosore_records(cfg)
    S["cosore_records"] = int(len(c))
    cols = KEEP + [x for x in ["srdb_row", "lat_str", "lon_str"] + EXTRA_SRDB if x not in KEEP]
    r = pd.concat([s.reindex(columns=cols), c.reindex(columns=cols)], ignore_index=True)
    r, cty = assign_countries(cfg, r)
    r = coordinate_check(cfg, r, cty)
    S["coord_mismatch_records"] = int(r.f_coord.sum())
    S["coord_mismatch_examples"] = (r[r.f_coord][["Country", "geo_country", "lat", "lon", "dist_to_reported_country_km"]]
                                    .drop_duplicates().head(40).astype(str).values.tolist())
    S["coord_reported_country_not_in_naturalearth"] = r.attrs.get("coord_unknown_reported_names", [])
    S["offland_records"] = int(r.f_offland.sum())
    r["log_rs"] = np.log(r.rs)

    base = r[~r.f_offland & ~r.f_coord]
    qc = base[~base[QC_FLAGS].any(axis=1)]
    S["records_after_coord_check"] = int(len(base))
    S["records_after_qc"] = int(len(qc))
    S["qc_removed_by"] = {f: int(base[f].sum()) for f in QC_FLAGS}
    S["qc_removed_any"] = int(base[QC_FLAGS].any(axis=1).sum())
    for name, rr in [("qc", qc), ("repo", base)]:
        st, site_of_record = to_sites(cfg, rr.reset_index(drop=True), name)
        r.loc[rr.index, f"site_id_{name}"] = site_of_record
        write_table(st, cfg.path("derived", f"sites_v3_{name}.parquet"))
        S[f"sites_{name}"] = {"n": int(len(st)), "by_continent": st.continent.value_counts().to_dict(),
                              "sites_with_2plus_records": int((st.n_rec >= 2).sum())}
    write_table(r, cfg.path("derived", "records_v3.parquet"))
    write_result(cfg, S, "build_sites.json")
    log.info("sites: qc %d, repo %d", S["sites_qc"]["n"], S["sites_repo"]["n"])
    return S
