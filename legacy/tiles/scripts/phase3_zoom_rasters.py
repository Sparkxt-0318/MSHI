"""
Phase 3: Multi-zoom raster generation in web mercator (EPSG:3857).

For each zoom level 0..6, generate a colorized RGBA raster of the
anomaly data at the appropriate resolution. These are NOT the final
tile pyramid (Phase 4 produces that with gdal2tiles); rather, they're
sanity-check artifacts showing the raster pyramid is structurally
sound.

Standard web mercator tile pyramid resolution at the equator (m/px):
  Z0: 156543.03   Z1: 78271.52   Z2: 39135.76   Z3: 19567.88
  Z4:   9783.94   Z5:  4891.97   Z6:  2445.98

The task description gives slightly different m/px labels but the
zoom-indexed pyramid I produce follows the standard.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.enums import Resampling as RsRes
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
IN_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"
INTERMED = ROOT / "tiles" / "intermediate"

VMIN, VMAX = 0.5, 1.5
CMAP = plt.get_cmap("RdBu_r").resampled(4096)
NORM = Normalize(vmin=VMIN, vmax=VMAX)

# Standard web mercator tile pyramid m/px at equator
ZOOM_RES_M = {
    0: 156543.03,
    1: 78271.52,
    2: 39135.76,
    3: 19567.88,
    4: 9783.94,
    5: 4891.97,
    6: 2445.98,
}


def apply_cmap_to_rgba(arr: np.ndarray) -> np.ndarray:
    """Return uint8 RGBA from float anomaly array."""
    rgba = CMAP(NORM(arr))
    mask = ~np.isfinite(arr)
    rgba[..., 3] = np.where(mask, 0.0, 1.0)
    return (rgba * 255).clip(0, 255).astype(np.uint8)


def reproject_to_3857(in_tif: Path) -> tuple[np.ndarray, dict]:
    """Reproject base raster to EPSG:3857. Return array + profile."""
    with rasterio.open(in_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:3857", src.width, src.height, *src.bounds
        )
        dst_arr = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:3857",
            resampling=Resampling.bilinear,
        )
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:3857",
            "transform": transform,
            "nodata": np.nan,
            "compress": "lzw",
            "tiled": True,
        }
    return dst_arr, profile


def downsample_to_resolution(arr: np.ndarray, profile: dict, target_res_m: float
                              ) -> tuple[np.ndarray, dict]:
    """Resample EPSG:3857 raster to target m/px."""
    src_res_x = abs(profile["transform"].a)
    src_res_y = abs(profile["transform"].e)
    scale_x = src_res_x / target_res_m
    scale_y = src_res_y / target_res_m
    new_w = max(1, int(round(profile["width"] * scale_x)))
    new_h = max(1, int(round(profile["height"] * scale_y)))

    # Build new transform: same origin, scaled pixel size
    t = profile["transform"]
    new_transform = rasterio.Affine(
        np.sign(t.a) * target_res_m, t.b, t.c,
        t.d, np.sign(t.e) * target_res_m, t.f,
    )

    dst = np.full((new_h, new_w), np.nan, dtype=np.float32)
    reproject(
        source=arr,
        destination=dst,
        src_transform=t,
        src_crs=profile["crs"],
        dst_transform=new_transform,
        dst_crs=profile["crs"],
        resampling=Resampling.average,
    )

    new_profile = {**profile,
                   "width": new_w, "height": new_h,
                   "transform": new_transform}
    return dst, new_profile


def main() -> int:
    print(f"Phase 3: reprojecting {IN_TIF} → EPSG:3857")
    master, master_profile = reproject_to_3857(IN_TIF)
    print(f"  master_3857: {master_profile['width']} x {master_profile['height']} "
          f"at {abs(master_profile['transform'].a):.1f} m/px")

    # Save master for reference
    with rasterio.open(INTERMED / "master_3857.tif", "w", **master_profile) as dst:
        dst.write(master, 1)

    zoom_sizes = {}
    for z in range(7):
        target_res = ZOOM_RES_M[z]
        print(f"  zoom {z}: target res {target_res:.0f} m/px")
        downsampled, dprofile = downsample_to_resolution(master, master_profile, target_res)

        # Save Float32 georef TIF
        tif_path = INTERMED / f"zoom{z}.tif"
        with rasterio.open(tif_path, "w", **dprofile) as dst:
            dst.write(downsampled, 1)

        # Apply cmap → RGBA PNG
        rgba_uint8 = apply_cmap_to_rgba(downsampled)
        png_path = INTERMED / f"zoom{z}.png"
        Image.fromarray(rgba_uint8, mode="RGBA").save(png_path, optimize=True)

        sz_tif = tif_path.stat().st_size
        sz_png = png_path.stat().st_size
        zoom_sizes[z] = {
            "tif_size": sz_tif,
            "png_size": sz_png,
            "width": dprofile["width"],
            "height": dprofile["height"],
            "res_m": target_res,
        }
        print(f"    {dprofile['width']}x{dprofile['height']}, "
              f"tif={sz_tif/1024:.1f}KB, png={sz_png/1024:.1f}KB")

    total = sum(z["tif_size"] + z["png_size"] for z in zoom_sizes.values())
    print(f"  total all zoom files: {total/1024/1024:.1f} MB")

    (INTERMED / "phase3_zoom_stats.json").write_text(
        json.dumps({"zooms": zoom_sizes,
                    "total_bytes": total,
                    "total_mb": total / 1024 / 1024}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
