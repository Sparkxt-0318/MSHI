"""
Phase 1: Rasterize the anomaly parquet to a base GeoTIFF.

Input:  data/outputs/hero_climate_npp_asia_anomaly.parquet
        columns: longitude, latitude, anomaly
Output: tiles/intermediate/asia_anomaly_base.tif
        EPSG:4326, Float32, NaN no-data, 0.05 deg resolution
        bbox: 25 to 180 lon, -10 to 80 lat
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[2]
IN_PARQUET = ROOT / "data" / "outputs" / "hero_climate_npp_asia_anomaly.parquet"
OUT_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"

BBOX = (25.0, -10.0, 180.0, 80.0)  # lon_min, lat_min, lon_max, lat_max
RES = 0.05  # degrees


def main() -> int:
    print(f"Phase 1: reading {IN_PARQUET}")
    df = pd.read_parquet(IN_PARQUET)
    print(f"  rows={len(df)} cols={list(df.columns)}")

    lon_min, lat_min, lon_max, lat_max = BBOX
    width = int(round((lon_max - lon_min) / RES))
    height = int(round((lat_max - lat_min) / RES))
    print(f"  raster dims: {width} x {height} (W x H)")

    # Build pixel indices. Lon increases east (col index), lat decreases
    # south (row index from top). Top row = lat_max.
    # Pixel center for (col, row) = (lon_min + (col+0.5)*RES, lat_max - (row+0.5)*RES)
    # So col = round((lon - lon_min)/RES - 0.5); row = round((lat_max - lat)/RES - 0.5)
    cols = np.round((df["longitude"].values - lon_min) / RES - 0.5).astype(np.int32)
    rows = np.round((lat_max - df["latitude"].values) / RES - 0.5).astype(np.int32)

    valid = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
    n_valid = int(valid.sum())
    print(f"  in-bounds cells: {n_valid} / {len(df)}")

    # Accept either column name: 'anomaly' (our canonical) or
    # 'mshi_geo_anomaly' (claude/item-1-modis source-branch convention).
    if "anomaly" in df.columns:
        value_col = "anomaly"
    elif "mshi_geo_anomaly" in df.columns:
        value_col = "mshi_geo_anomaly"
    else:
        raise KeyError(f"no anomaly column in {list(df.columns)}")
    print(f"  value column: {value_col}")
    raster = np.full((height, width), np.nan, dtype=np.float32)
    vals = df[value_col].values.astype(np.float32)
    raster[rows[valid], cols[valid]] = vals[valid]

    # Apply Natural Earth land mask if available (real-data parquet
    # from claude/item-1-modis already has ocean as finite values
    # because the model predicts everywhere; the land mask removes
    # ocean cells the synthetic regen would have NaN'd out).
    ne_mask_path = ROOT / "tiles" / "intermediate" / "land_mask.tif"
    if ne_mask_path.exists():
        with rasterio.open(ne_mask_path) as mds:
            mask_arr = mds.read(1).astype(bool)
        if mask_arr.shape == raster.shape:
            raster[~mask_arr] = np.nan
            print(f"  applied NE land mask: {100*mask_arr.mean():.1f}% land")

    transform = from_origin(lon_min, lat_max, RES, RES)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": np.nan,
        "compress": "lzw",
        "tiled": True,
    }
    with rasterio.open(OUT_TIF, "w", **profile) as dst:
        dst.write(raster, 1)
    print(f"  wrote {OUT_TIF}")
    print(f"  file size: {OUT_TIF.stat().st_size / 1024:.1f} KB")

    # Stats for audit
    finite = np.isfinite(raster)
    n_finite_px = int(finite.sum())
    rmin = float(np.nanmin(raster))
    rmax = float(np.nanmax(raster))
    rmean = float(np.nanmean(raster))
    print(f"  pixel stats: min={rmin:.3f} max={rmax:.3f} mean={rmean:.3f} "
          f"finite={n_finite_px}/{height*width}")

    stats = {
        "width": width, "height": height,
        "n_finite_px": n_finite_px,
        "pct_finite": n_finite_px / (width * height),
        "min": rmin, "max": rmax, "mean": rmean,
        "bbox": list(BBOX),
        "resolution_deg": RES,
        "crs": "EPSG:4326",
        "dtype": "float32",
    }
    (ROOT / "tiles" / "intermediate" / "phase1_raster_stats.json").write_text(
        json.dumps(stats, indent=2)
    )
    print("  stats written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
