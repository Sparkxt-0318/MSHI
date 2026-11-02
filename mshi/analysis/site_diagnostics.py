"""Diagnostics of the site build (exploratory; changes no table).

Quantifies the impact of choices kept from the handoff for reproduction (docs/DECISIONS.md D-P1-5):
1. the coordinate check measures "100 km from the reported country" in Web Mercator (EPSG:3857),
   where distances are inflated by 1/cos(latitude); compare with true (geodesic) distances;
2. the nearest-polygon continent fallback ("within 50 km") is also measured in EPSG:3857;
3. 5-km connected components can chain records that are more than 5 km apart.
Writes results/site_diagnostics.json.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS

from ..config import Config
from ..data.fetch import naturalearth_path
from ..io import read_table, write_json


def _true_km_to_polygon(lon: float, lat: float, geom, geom_crs) -> float:
    """Geodesic distance from a point to a polygon: distance in an azimuthal equidistant projection
    centred on the point (exact for distances measured from the centre)."""
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    g = gpd.GeoSeries([geom], crs=geom_crs).to_crs(aeqd).iloc[0]
    return float(g.distance(gpd.points_from_xy([0.0], [0.0])[0]) / 1000.0)


def _haversine_km(lat1, lon1, lat2, lon2, R=6371.0):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def site_diagnostics(cfg: Config) -> dict:
    cc = cfg["site_build"]["coord_check"]
    r = read_table(cfg, cfg.path("derived", "records_v3.parquet"))
    cty = gpd.read_file(naturalearth_path(cfg, "ne_50m_admin_0_countries.geojson"))[["ADMIN", "CONTINENT", "geometry"]]
    by_name = cty.set_index("ADMIN").geometry
    out: dict = {}

    # 1. coordinate check: Mercator vs true distance for every reported/polygon mismatch
    mism = r[(r.src == "srdb") & r.Country.notna() & r.geo_country.notna() & (r.reported_country_norm != r.geo_country)
             & r.dist_to_reported_country_km.notna()].copy()
    mism["true_km"] = [_true_km_to_polygon(lo, la, by_name.loc[n] if not isinstance(by_name.loc[n], gpd.GeoSeries)
                                           else by_name.loc[n].iloc[0], cty.crs)
                       for lo, la, n in zip(mism.lon, mism.lat, mism.reported_country_norm)]
    terr = {tuple(t) for t in cc["territory_exceptions"]}
    mism["terr"] = [(a, b) in terr for a, b in zip(mism.reported_country_norm, mism.geo_country)]
    flag_merc = (mism.dist_to_reported_country_km > cc["max_km"]) & ~mism.terr
    flag_true = (mism.true_km > cc["max_km"]) & ~mism.terr
    changed = mism[flag_merc != flag_true]
    out["coord_check"] = {
        "n_mismatch_checked": int(len(mism)),
        "flagged_mercator": int(flag_merc.sum()), "flagged_true_distance": int(flag_true.sum()),
        "flagged_mercator_only": int((flag_merc & ~flag_true).sum()),
        "flagged_true_only": int((~flag_merc & flag_true).sum()),
        "changed_records": changed[["rec_id", "Country", "geo_country", "lat", "lon", "dist_to_reported_country_km",
                                    "true_km", "f_method", "f_quality", "f_coverage", "f_ecosys", "f_dup"]]
        .round(3).to_dict(orient="records"),
        "mercator_over_true_median": float(np.median(mism.dist_to_reported_country_km / mism.true_km.clip(lower=1e-6))),
    }
    unknown = r[(r.src == "srdb") & r.Country.notna() & r.geo_country.notna()
                & (r.reported_country_norm != r.geo_country) & r.dist_to_reported_country_km.isna()]
    out["coord_check"]["reported_country_not_in_naturalearth"] = (
        unknown.groupby(["Country", "geo_country"]).size().rename("n").reset_index().to_dict(orient="records"))

    # 2. continent fallback for points off the 1:50m coastline
    off = r[r.f_offland]
    out["offland"] = {"n": int(len(off)), "records": []}
    for row in off.itertuples():
        d = sorted((_true_km_to_polygon(row.lon, row.lat, g, cty.crs), a) for a, g in zip(cty.ADMIN, cty.geometry)
                   if g.distance(gpd.points_from_xy([row.lon], [row.lat])[0]) < 5)[:1]
        out["offland"]["records"].append({"rec_id": row.rec_id, "lat": row.lat, "lon": row.lon,
                                          "nearest_country": d[0][1] if d else None,
                                          "true_km": round(d[0][0], 1) if d else None})

    # 3. chaining: largest record-to-record distance inside each site
    for tag in cfg["site_build"]["variants"]:
        col = f"site_id_{tag}"
        rr = r[r[col].notna()]
        diam = {}
        for sid, g in rr.groupby(col):
            if len(g) < 2:
                continue
            la, lo = g.lat.values, g.lon.values
            i, j = np.triu_indices(len(g), 1)
            diam[sid] = float(_haversine_km(la[i], lo[i], la[j], lo[j]).max())
        dv = pd.Series(diam, dtype=float)
        out[f"site_diameter_{tag}"] = {"n_multi_record_sites": int(len(dv)),
                                       "n_gt_5km": int((dv > 5).sum()), "n_gt_10km": int((dv > 10).sum()),
                                       "n_gt_20km": int((dv > 20).sum()), "max_km": float(dv.max()) if len(dv) else None,
                                       "largest": dv.sort_values(ascending=False).head(5).round(1).to_dict()}
    write_json(out, cfg.path("results", "site_diagnostics.json"))
    return {k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if not isinstance(vv, list)})
            for k, v in out.items()}
