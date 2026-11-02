"""Attach gridded features to the v3 site tables.

Port of ``docs/handoff/scripts/features_v3.py``: nearest-pixel sampling of WorldClim 2.1 2.5'
(bio01-bio19; values below -1e30 are missing) and SoilGrids 2.0 5-15 cm mean at 0.05 deg
(values <= 0 are missing; scaled to conventional units), plus the MODIS window means from
``modis_points`` merged on ``site_key``; lst_diurnal_range = lst_day - lst_night.

Inputs are used only if they are the recorded outputs of current upstream results: the site tables
(build_sites.json), the MODIS table (modis_points.json, plus its own cache key) and every raster
(fetch_worldclim.json, fetch_soilgrids.json); so a raster replaced on disk, or fetched under another
config, is refused (mshi.io.require_outputs).

Feature tables go to data/interim/ (gitignored): they contain WorldClim-derived values and
WorldClim's redistribution terms are [UNVERIFIED] (see docs/DECISIONS.md).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import Config
from ..io import read_json, read_table, require_outputs, write_result, write_table
from .modis import load_modis_points, site_key
from .rasters import soilgrids_path, worldclim_path

log = logging.getLogger("mshi.features")


def sample_raster(path, lon, lat) -> np.ndarray:
    """Nearest-pixel values at points (rasterio ``sample``); the raster's nodata -> NaN."""
    import rasterio
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], dtype="float64")
        if s.nodata is not None:
            v[v == s.nodata] = np.nan
    return v


def attach_features(cfg: Config, d: pd.DataFrame, modis: pd.DataFrame | None) -> pd.DataFrame:
    w = cfg["sources"]["worldclim"]
    sg = cfg["sources"]["soilgrids"]
    d = d.copy()
    lon, lat = d.lon.values, d.lat.values
    for i in range(1, cfg["features"]["worldclim_vars"] + 1):
        v = sample_raster(worldclim_path(cfg, i), lon, lat)
        d[f"bio{i:02d}"] = np.where(v < w["nodata_below"], np.nan, v)
    for k in sg["variables"]:
        v = sample_raster(soilgrids_path(cfg, k), lon, lat)
        d[k] = np.where(v > 0, v * sg["scale"][k], np.nan) if sg["zero_is_missing"] else v * sg["scale"][k]
    d["site_key"] = site_key(d.lat, d.lon, cfg["features"]["site_key_round"]).values
    if modis is not None:
        keep = ["site_key"] + [c for c in ["npp", "npp_n", "lst_day", "lst_night"] if c in modis]
        d = d.merge(modis[keep], on="site_key", how="left")
        if {"lst_day", "lst_night"} <= set(d.columns):
            d["lst_diurnal_range"] = d.lst_day - d.lst_night
    return d


def verify_inputs(cfg: Config) -> None:
    """Refuse (StaleInputError) unless every input file is a recorded output of a current upstream result."""
    tags = cfg["site_build"]["variants"]
    require_outputs(cfg, "build_sites.json", [cfg.path("derived", f"sites_v3_{t}.parquet") for t in tags])
    require_outputs(cfg, "modis_points.json", [cfg.path("interim", "modis_points.parquet")])
    require_outputs(cfg, "fetch_worldclim.json",
                    [worldclim_path(cfg, i) for i in range(1, cfg["features"]["worldclim_vars"] + 1)])
    require_outputs(cfg, "fetch_soilgrids.json",
                    [soilgrids_path(cfg, v) for v in cfg["sources"]["soilgrids"]["variables"]])


def features(cfg: Config) -> dict:
    nd = cfg["features"]["site_key_round"]
    verify_inputs(cfg)
    sites = {tag: read_table(cfg, cfg.path("derived", f"sites_v3_{tag}.parquet"))
             for tag in cfg["site_build"]["variants"]}
    keys = set().union(*(site_key(d.lat, d.lon, nd) for d in sites.values()))
    # refuses MODIS values from another MODIS config/extraction code/libraries, from a run with failed
    # reads, changed after the extraction, or not covering every site
    modis = load_modis_points(cfg, keys)
    res = {"modis_cache_key": read_json(cfg.path("interim", "modis_points.meta.json"))["key"]}
    outputs = []
    for tag, d in sites.items():
        d = attach_features(cfg, d, modis)
        outputs.append(write_table(d, cfg.path("interim", f"features_v3_{tag}.parquet")))
        res[tag] = {"shape": list(d.shape),
                    "missing": d[["bio01", "bio12", "clay", "npp", "lst_day"]].isna().sum().to_dict()}
    write_result(cfg, res, "features.json", outputs=outputs,
                 inputs=["build_sites.json", "modis_points.json", "fetch_worldclim.json", "fetch_soilgrids.json"])
    return res
