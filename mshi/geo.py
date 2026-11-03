"""Geodesic distances and the geographic continent, for everything new in v3 (docs/DECISIONS.md D-C1-2,
D-C1-5, D-P2-2, D-P2-3).

The locked site build (``mshi.data.sites``) measures the coordinate check in Web Mercator and labels each
site with the continent of the country polygon that contains it; both are kept only to reproduce the locked
test. Everything new uses this module:

- ``geodesic_km``: the distance from a point to a (multi)polygon, measured in an azimuthal equidistant
  projection centred on the point (WGS84). Distances from the centre of that projection are geodesic, so the
  result is exact up to the polygon's vertex spacing. The polygon is first clipped to a lon/lat window around
  the point, so far-away parts (which an azimuthal projection distorts near the antipode) never produce a
  spurious short distance; anything beyond ``max_km`` is reported as ``inf``.
- ``geographic_continent``: the continent of the Natural Earth 1:50m admin-0 *map subunit* that contains the
  point. Natural Earth splits overseas territories into their own subunits and gives each the continent where
  it lies (French Guiana: South America; the Canary Islands and Madeira: Africa; Hawaii and Easter Island:
  Oceania; Guadeloupe and Martinique: North America; Svalbard: Europe). Subunits labelled "Seven seas (open
  ocean)" take their UN region; the UN Americas region is split by UN sub-region: North America for the
  sub-regions in ``site_build_analysis.geo_continent.americas_north_subregions`` (Northern America, Central
  America, Caribbean), South America otherwise (South Georgia and the South Sandwich Islands, whose sub-region
  is the open ocean, included; D-P2-12). Russia keeps the locked split at
  ``site_build.continent.russia_split_lon`` (Natural Earth's subunits split Russia along another line, and only
  overseas territories were to change), with one correction (D-P2-12): Europe is 0 <= lon < the split, so the
  Russian land east of the antimeridian (negative longitude: eastern Chukotka, part of Wrangel Island) is Asia.
  Countries spanning two continents other than Russia stay whole (Turkey, Kazakhstan, Egypt, ...).
  Points off the 1:50m coastline take the nearest subunit within ``site_build.continent.nearest_max_m``,
  measured geodesically; points farther from land get None.
"""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import Point, box
from shapely.ops import transform, unary_union

from .config import Config
from .netutil import verify_sha256

OPEN_OCEAN = "Seven seas (open ocean)"


def _window(lon: float, lat: float, deg_lat: float):
    """Lon/lat box around a point that contains every location within ``deg_lat`` degrees of arc,
    split at the antimeridian."""
    lat0, lat1 = max(-90.0, lat - deg_lat), min(90.0, lat + deg_lat)
    c = math.cos(math.radians(min(89.0, max(abs(lat0), abs(lat1)))))
    dlon = 180.0 if (lat1 >= 89.0 or lat0 <= -89.0) else min(180.0, deg_lat / max(c, 1e-6))
    lo, hi = lon - dlon, lon + dlon
    if dlon >= 180.0:
        return box(-180.0, lat0, 180.0, lat1)
    parts = [box(max(lo, -180.0), lat0, min(hi, 180.0), lat1)]
    if lo < -180.0:
        parts.append(box(lo + 360.0, lat0, 180.0, lat1))
    if hi > 180.0:
        parts.append(box(-180.0, lat0, hi - 360.0, lat1))
    return unary_union(parts)


def geodesic_km(lon: float, lat: float, geom, max_km: float = 2000.0) -> float:
    """Geodesic distance (km) from (lon, lat) to ``geom`` (lon/lat, EPSG:4326); 0 inside; ``inf`` if no
    part of ``geom`` lies within about ``max_km``."""
    if geom is None or geom.is_empty:
        return math.inf
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.contains(Point(lon, lat)):
        return 0.0
    near = geom.intersection(_window(lon, lat, max_km / 111.0 + 1.0))
    if near.is_empty:
        return math.inf
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    tf = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    d = transform(tf.transform, near).distance(Point(0.0, 0.0)) / 1000.0
    return float(d) if d <= max_km else math.inf


def nearest_within_km(lon: float, lat: float, geoms: gpd.GeoSeries, max_km: float) -> tuple[int | None, float]:
    """(index label, km) of the geometry in ``geoms`` nearest to the point, if within ``max_km``; else
    (None, inf). Candidates are pre-selected by a lon/lat window, then measured geodesically."""
    win = _window(lon, lat, max_km / 111.0 + 1.0)
    cand = geoms[geoms.intersects(win)]
    best, best_km = None, math.inf
    for idx, g in cand.items():
        km = geodesic_km(lon, lat, g, max_km=max_km)
        if km < best_km:
            best, best_km = idx, km
    return (best, best_km) if best_km <= max_km else (None, math.inf)


def subunits(cfg: Config) -> gpd.GeoDataFrame:
    """Natural Earth 1:50m map subunits (hash-verified) with ``continent_geo`` per subunit (module docstring)."""
    from .data.fetch import naturalearth_path
    gc = cfg["site_build_analysis"]["geo_continent"]
    f = gc["subunits_file"]
    verify_sha256(naturalearth_path(cfg, f), cfg["sources"]["naturalearth"]["files"][f])
    su = gpd.read_file(naturalearth_path(cfg, f))[["ADMIN", "SUBUNIT", "CONTINENT", "REGION_UN", "SUBREGION",
                                                   "geometry"]]
    americas = np.where(su.SUBREGION.isin(list(gc["americas_north_subregions"])), "North America", "South America")
    region = np.where(su.REGION_UN.eq("Americas"), americas, su.REGION_UN)
    su["continent_geo"] = np.where(su.CONTINENT.eq(OPEN_OCEAN), region, su.CONTINENT)
    su["geometry"] = [g if g.is_valid else make_valid(g) for g in su.geometry]
    return su.reset_index(drop=True)


def geographic_continent(cfg: Config, lon, lat, su: gpd.GeoDataFrame | None = None) -> pd.DataFrame:
    """Per point: ``continent_geo``, the subunit and its country (module docstring), and the geodesic
    distance to it (0 inside, km for an off-coast point matched within the limit)."""
    sb = cfg["site_build"]["continent"]
    su = subunits(cfg) if su is None else su
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    pts = gpd.GeoDataFrame({"i": np.arange(len(lon))}, geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, su, how="left", predicate="within")
    j = j[~j.index.duplicated()].sort_values("i")
    out = pd.DataFrame({"continent_geo": j.continent_geo.values, "geo_subunit": j.SUBUNIT.values,
                        "geo_subunit_admin": j.ADMIN.values, "geo_subunit_km": np.where(j.SUBUNIT.notna(), 0.0, np.nan)})
    max_km = sb["nearest_max_m"] / 1000.0
    for i in np.where(out.geo_subunit.isna().values)[0]:
        k, km = nearest_within_km(lon[i], lat[i], su.geometry, max_km)
        if k is not None:
            out.loc[i, ["continent_geo", "geo_subunit", "geo_subunit_admin"]] = su.loc[k, ["continent_geo", "SUBUNIT",
                                                                                           "ADMIN"]].values
            out.loc[i, "geo_subunit_km"] = km
    rus = out.geo_subunit_admin.eq("Russia").values
    europe = (lon[rus] >= 0.0) & (lon[rus] < sb["russia_split_lon"])    # lon < 0: east of the antimeridian
    out.loc[rus, "continent_geo"] = np.where(europe, "Europe", "Asia")
    return out
