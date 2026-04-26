"""
features.py — extract feature stack at training points and across the grid.

Two main entry points:
  - extract_at_points(points_df, raster_paths)  → DataFrame
  - build_prediction_grid(bbox, resolution_deg, raster_paths) → DataFrame

Both produce a clean tabular feature matrix that the model can consume.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Optional heavy imports — fail gracefully so the synthetic demo still runs.
try:
    import rasterio
    from rasterio.sample import sample_gen
    from rasterio.transform import from_bounds
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

LOG = logging.getLogger("mshi_geo.features")


# ─────────────────────────────────────────────────────────────────────────────
# Point sampling
# ─────────────────────────────────────────────────────────────────────────────
def sample_raster_at_points(
    raster_path: Path,
    lons: np.ndarray,
    lats: np.ndarray,
    band: int = 1,
    nodata_mask: Optional[float] = None,
) -> np.ndarray:
    """Sample a single-band raster at given (lon, lat) coordinates."""
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio not installed; install requirements.txt")

    with rasterio.open(raster_path) as src:
        coords = list(zip(lons, lats))
        vals = np.array(
            [v[band - 1] if v is not None else np.nan for v in src.sample(coords)],
            dtype="float64",
        )
        if nodata_mask is None:
            nodata_mask = src.nodata
        if nodata_mask is not None:
            vals = np.where(vals == nodata_mask, np.nan, vals)
    return vals


def extract_at_points(
    points: pd.DataFrame,
    raster_registry: Dict[str, Path],
    lon_col: str = "longitude",
    lat_col: str = "latitude",
) -> pd.DataFrame:
    """
    Build a feature table for a DataFrame of training/validation points.

    Parameters
    ----------
    points : DataFrame with at minimum [longitude, latitude]
    raster_registry : {feature_name: path_to_geotiff}
    """
    out = points.copy()
    lons = out[lon_col].to_numpy()
    lats = out[lat_col].to_numpy()
    for feat, path in raster_registry.items():
        path = Path(path)
        if not path.exists():
            LOG.warning("Missing raster for feature %s: %s — filling NaN", feat, path)
            out[feat] = np.nan
            continue
        out[feat] = sample_raster_at_points(path, lons, lats)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Prediction grid builder
# ─────────────────────────────────────────────────────────────────────────────
def build_grid_coords(
    bbox: List[float], resolution_deg: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (lon, lat) 1-D arrays for a regular grid covering bbox."""
    lon_min, lat_min, lon_max, lat_max = bbox
    lons = np.arange(lon_min + resolution_deg / 2, lon_max, resolution_deg)
    lats = np.arange(lat_min + resolution_deg / 2, lat_max, resolution_deg)
    return lons, lats


def build_prediction_grid(
    bbox: List[float],
    resolution_deg: float,
    raster_registry: Dict[str, Path],
    chunk_rows: int = 200,
) -> pd.DataFrame:
    """
    Build a prediction-ready DataFrame with one row per grid cell.

    Each row carries (lon, lat) and one column per feature, sampled from the
    associated raster. Memory-efficient: processes the grid row-by-row chunks.
    """
    lons, lats = build_grid_coords(bbox, resolution_deg)
    LOG.info("Grid size: %d x %d = %.2f M cells", len(lons), len(lats),
             len(lons) * len(lats) / 1e6)

    chunks: List[pd.DataFrame] = []
    for i0 in range(0, len(lats), chunk_rows):
        chunk_lats = lats[i0 : i0 + chunk_rows]
        gx, gy = np.meshgrid(lons, chunk_lats)
        df = pd.DataFrame({
            "longitude": gx.ravel(),
            "latitude": gy.ravel(),
        })
        for feat, path in raster_registry.items():
            df[feat] = sample_raster_at_points(
                Path(path), df["longitude"].to_numpy(), df["latitude"].to_numpy()
            )
        chunks.append(df)
    return pd.concat(chunks, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering helpers
# ─────────────────────────────────────────────────────────────────────────────
def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add ratio/derivative features that often help soil models."""
    out = df.copy()
    if "soc" in out and "nitrogen" in out:
        out["c_n_ratio"] = out["soc"] / (out["nitrogen"].replace(0, np.nan))
    if "clay" in out and "sand" in out:
        out["clay_sand_ratio"] = out["clay"] / (out["sand"].replace(0, np.nan))
    if "phh2o" in out:
        # Closeness to optimal microbial pH (~6.5). Handles SoilGrids pH*10 if needed.
        ph = out["phh2o"]
        ph = np.where(ph > 14, ph / 10.0, ph)
        out["ph_optimality"] = -np.abs(ph - 6.5)
    if "bio01" in out and "bio12" in out:
        # Crude aridity index: precip / (temp+10) — simplified De Martonne
        out["aridity_demartonne"] = out["bio12"] / (out["bio01"] + 10.0)
    if "lst_day" in out and "lst_night" in out:
        out["lst_diurnal_range"] = out["lst_day"] - out["lst_night"]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Default raster registry (config-driven in run.sh)
# ─────────────────────────────────────────────────────────────────────────────
def default_registry(raw_dir: Path) -> Dict[str, Path]:
    """Return the canonical mapping of feature name → raster path."""
    sg = raw_dir / "soilgrids"
    wc = raw_dir / "worldclim"
    md = raw_dir / "modis"
    return {
        # SoilGrids 0–30cm means
        "soc":      sg / "soc_0-30cm_asia_1000m.tif",
        "nitrogen": sg / "nitrogen_0-30cm_asia_1000m.tif",
        "phh2o":    sg / "phh2o_0-30cm_asia_1000m.tif",
        "clay":     sg / "clay_0-30cm_asia_1000m.tif",
        "sand":     sg / "sand_0-30cm_asia_1000m.tif",
        "silt":     sg / "silt_0-30cm_asia_1000m.tif",
        "bdod":     sg / "bdod_0-30cm_asia_1000m.tif",
        "cec":      sg / "cec_0-30cm_asia_1000m.tif",
        # WorldClim
        "bio01":    wc / "wc2.1_30s_bio_1.tif",
        "bio04":    wc / "wc2.1_30s_bio_4.tif",
        "bio05":    wc / "wc2.1_30s_bio_5.tif",
        "bio06":    wc / "wc2.1_30s_bio_6.tif",
        "bio12":    wc / "wc2.1_30s_bio_12.tif",
        "bio14":    wc / "wc2.1_30s_bio_14.tif",
        "bio15":    wc / "wc2.1_30s_bio_15.tif",
        "bio17":    wc / "wc2.1_30s_bio_17.tif",
        # MODIS
        "npp":        md / "npp_2020_2024_mean.tif",
        "lst_day":    md / "lst_day_2020_2024_mean.tif",
        "lst_night":  md / "lst_night_2020_2024_mean.tif",
        "landcover":  md / "landcover_igbp_2023.tif",
    }
