"""Attach gridded features to the v3 site tables.

Port of ``docs/handoff/scripts/features_v3.py``: nearest-pixel sampling of WorldClim 2.1 2.5'
(bio01-bio19; values below -1e30 are missing) and SoilGrids 2.0 5-15 cm mean at 0.05 deg
(values <= 0 are missing; scaled to conventional units), plus the MODIS window means from
``modis_points`` merged on ``site_key``; lst_diurnal_range = lst_day - lst_night.

Feature tables go to data/interim/ (gitignored): they contain WorldClim-derived values and
WorldClim's redistribution terms are [UNVERIFIED] (see docs/DECISIONS.md).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import Config
from ..io import read_table, write_json, write_table
from .modis import site_key
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


def features(cfg: Config) -> dict:
    mp = cfg.path("interim", "modis_points.parquet")
    modis = pd.read_parquet(mp) if mp.exists() else None
    if modis is None:
        raise FileNotFoundError(f"{mp} missing; run stage modis_points first")
    res = {}
    for tag in cfg["site_build"]["variants"]:
        d = read_table(cfg, cfg.path("derived", f"sites_v3_{tag}.parquet"))
        d = attach_features(cfg, d, modis)
        write_table(d, cfg.path("interim", f"features_v3_{tag}.parquet"))
        res[tag] = {"shape": list(d.shape),
                    "missing": d[["bio01", "bio12", "clay", "npp", "lst_day"]].isna().sum().to_dict()}
    write_json(res, cfg.path("results", "features.json"))
    return res
