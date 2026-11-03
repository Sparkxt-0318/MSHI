"""A global land grid with WorldClim climate and the geographic continent (Phase 2: the prediction domain of
kNNDM cross-validation and the area-of-applicability map).

Cell centres on a regular ``deg`` grid; each WorldClim 2.1 bioclim layer is sampled at the centre (nearest
2.5' pixel, values below ``sources.worldclim.nodata_below`` are missing, as for sites) and a cell is kept if
every bioclim layer has a value. Cell area is the exact area of the lon/lat cell on a sphere of radius
``site_build.earth_radius_km``. ``continent_geo`` comes from ``mshi.geo.geographic_continent`` (the same rule
as for sites, overseas territories by location). Rasters are used only as the recorded outputs of a current
``fetch_worldclim`` result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..data.features import sample_raster
from ..data.rasters import worldclim_path
from ..geo import geographic_continent, subunits
from ..io import require_outputs


def cell_area_km2(lat_c: np.ndarray, deg: float, radius_km: float) -> np.ndarray:
    """Exact area of lon/lat cells of size ``deg`` centred at latitudes ``lat_c`` on a sphere."""
    lat0, lat1 = np.radians(lat_c - deg / 2), np.radians(lat_c + deg / 2)
    return radius_km ** 2 * np.radians(deg) * (np.sin(lat1) - np.sin(lat0))


def climate_grid(cfg: Config, deg: float, with_continent: bool = True) -> pd.DataFrame:
    n = cfg["features"]["worldclim_vars"]
    tifs = [worldclim_path(cfg, i) for i in range(1, n + 1)]
    require_outputs(cfg, "fetch_worldclim.json", tifs)
    lon, lat = np.meshgrid(np.arange(-180 + deg / 2, 180, deg), np.arange(-90 + deg / 2, 90, deg))
    g = pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel()})
    below = cfg["sources"]["worldclim"]["nodata_below"]
    for i, t in enumerate(tifs, start=1):
        v = sample_raster(t, g.lon.values, g.lat.values)
        g[f"bio{i:02d}"] = np.where(v < below, np.nan, v)
    g = g.dropna().reset_index(drop=True)
    g["area_km2"] = cell_area_km2(g.lat.values, deg, cfg["site_build"]["earth_radius_km"])
    if with_continent:
        c = geographic_continent(cfg, g.lon.values, g.lat.values, subunits(cfg))
        g["continent_geo"] = c.continent_geo.values
    return g
