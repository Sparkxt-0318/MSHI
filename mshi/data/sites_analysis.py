"""The site build for v3's own analyses (author's decisions Q-2, Q-5 and Q-6 of 2026-11-03; docs/DECISIONS.md
D-P2-1 to D-P2-3).

The locked build (``mshi.data.sites``) is kept unchanged to reproduce the locked test. This build applies the
same SRDB records, filters, thresholds, 5-km site merging and site-id scheme, except:

1. COSORE comes from ``cosore_annual_analysis`` (untreated soil-respiration ports with full-year coverage);
2. distances are geodesic (``mshi.geo.geodesic_km``): a record outside every 1:50m country polygon takes the
   nearest country within ``site_build.continent.nearest_max_m`` (locked build: Web Mercator), and the
   coordinate check measures the distance to the reported country (locked build: Web Mercator), with the same
   100-km threshold, aliases and territory exceptions;
3. every record and site gets a geographic continent ``continent_geo`` (``mshi.geo.geographic_continent``:
   overseas territories by location) next to the locked, country-based ``continent``. All new work uses
   ``continent_geo``. A record with no country or no subunit within the limit is off land.

Outputs: data/derived/records_analysis.parquet, sites_analysis_{qc,repo}.parquet (site ids ``v3aqc_*``,
``v3arepo_*``) and results/build_sites_analysis.json: counts, and how the tables differ from the locked ones
(coordinate-check flags, COSORE sites, continents). Exploratory inputs, not reproduction targets.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import make_valid

from ..config import Config
from ..geo import geographic_continent, geodesic_km, nearest_within_km, subunits
from ..io import read_table, require_outputs, write_result, write_table
from ..netutil import verify_sha256
from .fetch import naturalearth_path
from .sites import EXTRA_SRDB, KEEP, QC_FLAGS, load_cosore_records, load_srdb_records, to_sites

log = logging.getLogger("mshi.sites_analysis")

LOCKED_TABLES = ("records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet")
TABLES = ("records_analysis.parquet", "sites_analysis_qc.parquet", "sites_analysis_repo.parquet")


def countries(cfg: Config) -> gpd.GeoDataFrame:
    ne_file = "ne_50m_admin_0_countries.geojson"
    verify_sha256(naturalearth_path(cfg, ne_file), cfg["sources"]["naturalearth"]["files"][ne_file])
    cty = gpd.read_file(naturalearth_path(cfg, ne_file))[["ADMIN", "NAME", "CONTINENT", "geometry"]]
    cty["geometry"] = [g if g.is_valid else make_valid(g) for g in cty.geometry]
    return cty


def assign_countries_geodesic(cfg: Config, r: pd.DataFrame, cty: gpd.GeoDataFrame) -> pd.DataFrame:
    """Country (point in polygon, else nearest within the limit, geodesic) and the locked, country-based
    continent (Russia split at ``russia_split_lon``)."""
    cont = cfg["site_build"]["continent"]
    g = gpd.GeoDataFrame(r[["lon", "lat"]].copy(), geometry=gpd.points_from_xy(r.lon, r.lat), crs=4326)
    j = gpd.sjoin(g, cty, how="left", predicate="within")
    j = j[~j.index.duplicated()].reindex(r.index)
    r = r.copy()
    r["geo_country"], r["continent"] = j.ADMIN.values, j.CONTINENT.values
    r["country_km"] = np.where(j.ADMIN.notna(), 0.0, np.nan)
    max_km = cont["nearest_max_m"] / 1000.0
    for i in np.where(r.geo_country.isna().values)[0]:
        k, km = nearest_within_km(r.lon.iat[i], r.lat.iat[i], cty.geometry, max_km)
        if k is not None:
            r.iloc[i, r.columns.get_indexer(["geo_country", "continent", "country_km"])] = [
                cty.loc[k, "ADMIN"], cty.loc[k, "CONTINENT"], km]
    rus = r.geo_country.eq("Russia")
    r.loc[rus, "continent"] = np.where(r.loc[rus, "lon"] >= cont["russia_split_lon"], "Asia", "Europe")
    return r


def coordinate_check_geodesic(cfg: Config, r: pd.DataFrame, cty: gpd.GeoDataFrame) -> pd.DataFrame:
    """The locked coordinate check (``mshi.data.sites.coordinate_check``) with the distance to the reported
    country measured geodesically."""
    cc = cfg["site_build"]["coord_check"]
    far = cfg["site_build_analysis"]["max_far_km"]
    rep = r.Country.astype(str).str.strip().map(lambda x: cc["aliases"].get(x, x))
    mism = (r.src == "srdb") & r.Country.notna() & r.geo_country.notna() & (rep != r.geo_country)
    geom = cty.set_index("ADMIN").geometry
    dist = np.full(len(r), np.nan)
    unknown = []
    for i in np.where(mism.values)[0]:
        name = rep.iat[i]
        if name in geom.index:
            gg = geom.loc[name]
            gg = gg.iloc[0] if isinstance(gg, gpd.GeoSeries) else gg
            dist[i] = geodesic_km(r.lon.iat[i], r.lat.iat[i], gg, max_km=far)
        else:
            unknown.append(name)
    r = r.copy()
    r["reported_country_norm"] = rep.values
    r["dist_to_reported_country_km"] = dist          # geodesic; inf = farther than max_far_km
    terr = {tuple(t) for t in cc["territory_exceptions"]}
    is_terr = pd.Series([(a, b) in terr for a, b in zip(rep, r.geo_country)], index=r.index)
    r["f_coord"] = mism & (r.dist_to_reported_country_km > cc["max_km"]) & ~is_terr
    r.attrs["coord_unknown_reported_names"] = sorted(set(map(str, unknown)))
    return r


def _mode(x: pd.Series):
    x = x.dropna()
    return x.mode().iat[0] if len(x) else np.nan


def build_sites_analysis(cfg: Config) -> dict:
    S: dict = {"exploratory": True}
    s, info = load_srdb_records(cfg)          # pinned SRDB bytes, the same filters as the locked build
    S.update(info)
    c = load_cosore_records(cfg, table="cosore_annual_analysis.csv", result="cosore_annual_analysis.json")
    S["cosore_records"] = int(len(c))
    cols = KEEP + [x for x in ["srdb_row", "lat_str", "lon_str"] + EXTRA_SRDB if x not in KEEP]
    r = pd.concat([s.reindex(columns=cols), c.reindex(columns=cols)], ignore_index=True)
    cty = countries(cfg)
    r = assign_countries_geodesic(cfg, r, cty)
    r = coordinate_check_geodesic(cfg, r, cty)
    geo = geographic_continent(cfg, r.lon.values, r.lat.values, subunits(cfg))
    r["continent_geo"], r["geo_subunit"] = geo.continent_geo.values, geo.geo_subunit.values
    r["f_offland"] = r.continent.isna() | r.continent_geo.isna()
    r["log_rs"] = np.log(r.rs)
    base = r[~r.f_offland & ~r.f_coord]
    qc = base[~base[QC_FLAGS].any(axis=1)]
    S["coord_mismatch_records"] = int(r.f_coord.sum())
    S["offland_records"] = int(r.f_offland.sum())
    S["records_after_coord_check"] = int(len(base))
    S["records_after_qc"] = int(len(qc))
    S["qc_removed_by"] = {f: int(base[f].sum()) for f in QC_FLAGS}
    S["coord_reported_country_not_in_naturalearth"] = r.attrs.get("coord_unknown_reported_names", [])
    outputs, tables = [], {}
    for name, rr in [("qc", qc), ("repo", base)]:
        rr = rr.reset_index()
        st, site_of_record = to_sites(cfg, rr.drop(columns="index"), f"a{name}")
        r.loc[rr["index"].values, f"site_id_{name}"] = site_of_record
        by_site = pd.DataFrame({"site_id": site_of_record, "continent_geo": rr.continent_geo.values,
                                "geo_subunit": rr.geo_subunit.values}).groupby("site_id")
        st["continent_geo"] = st.site_id.map(by_site.continent_geo.agg(_mode))
        st["geo_subunit"] = st.site_id.map(by_site.geo_subunit.agg(_mode))
        tables[name] = st
        outputs.append(write_table(st, cfg.path("derived", f"sites_analysis_{name}.parquet")))
        S[f"sites_{name}"] = {"n": int(len(st)), "by_continent_geo": st.continent_geo.value_counts().to_dict(),
                              "by_continent_locked_rule": st.continent.value_counts().to_dict(),
                              "continent_geo_differs": st[st.continent != st.continent_geo][
                                  ["site_id", "lat", "lon", "country", "geo_subunit", "continent", "continent_geo"]]
                              .round(4).to_dict(orient="records")}
    outputs.insert(0, write_table(r, cfg.path("derived", "records_analysis.parquet")))
    ins = ["cosore_annual_analysis.json"]
    if cfg.out_root is None:                  # informational; smoke runs subset the locked build afterwards
        S["vs_locked_build"] = compare_with_locked(cfg, r, tables)
        ins.append("build_sites.json")
    write_result(cfg, S, "build_sites_analysis.json", outputs=outputs, inputs=ins)
    log.info("analysis sites: qc %d, repo %d", S["sites_qc"]["n"], S["sites_repo"]["n"])
    return {k: v for k, v in S.items() if k not in ("vs_locked_build",)}


def compare_with_locked(cfg: Config, r: pd.DataFrame, tables: dict) -> dict:
    """How the analysis tables differ from the locked ones (informational)."""
    paths = [cfg.path("derived", f) for f in LOCKED_TABLES]
    require_outputs(cfg, "build_sites.json", paths)
    lr = read_table(cfg, paths[0])
    m = r[["rec_id", "f_coord", "dist_to_reported_country_km", "Country", "geo_country"]].merge(
        lr[["rec_id", "f_coord", "dist_to_reported_country_km"]], on="rec_id", how="outer",
        suffixes=("_geodesic", "_locked"), indicator=True)
    both = m[m._merge == "both"]
    changed = both[both.f_coord_geodesic != both.f_coord_locked]
    out = {"records_only_in_analysis": int((m._merge == "left_only").sum()),
           "records_only_in_locked": int((m._merge == "right_only").sum()),
           "coord_flag": {"locked_mercator": int(both.f_coord_locked.sum()),
                          "geodesic": int(both.f_coord_geodesic.sum()),
                          "flag_changed": changed[["rec_id", "Country", "geo_country", "dist_to_reported_country_km_locked",
                                                   "dist_to_reported_country_km_geodesic", "f_coord_locked",
                                                   "f_coord_geodesic"]]
                          .round(2).to_dict(orient="records")}}
    lc = r[r.src == "cosore"].rec_id
    old = lr[lr.src == "cosore"].rec_id
    out["cosore_sites"] = {"locked": int(old.nunique()), "analysis": int(lc.nunique()),
                           "dropped": sorted(set(old) - set(lc)), "added": sorted(set(lc) - set(old))}
    for name, st in tables.items():
        locked = read_table(cfg, cfg.path("derived", f"sites_v3_{name}.parquet"))
        out[f"sites_{name}"] = {"locked": int(len(locked)), "analysis": int(len(st))}
    return out
