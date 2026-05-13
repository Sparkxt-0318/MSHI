"""
Phase 4 step 1: Create a colorized RGBA GeoTIFF (EPSG:4326) for input
to gdal_translate -of MBTiles. Source is the base Float32 anomaly TIF.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[2]
IN_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"
OUT_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_rgba.tif"

VMIN, VMAX = 0.5, 1.5


def main() -> int:
    print(f"Phase 4 colorize: reading {IN_TIF}")
    with rasterio.open(IN_TIF) as src:
        arr = src.read(1)
        profile = src.profile.copy()

    cmap = plt.get_cmap("RdBu_r").resampled(4096)
    norm = Normalize(vmin=VMIN, vmax=VMAX)
    rgba = cmap(norm(arr))
    mask = ~np.isfinite(arr)
    rgba[..., 3] = np.where(mask, 0.0, 1.0)
    rgba_uint8 = (rgba * 255).clip(0, 255).astype(np.uint8)

    # Save as 4-band RGBA GeoTIFF, same CRS and transform as input
    profile.update(
        dtype="uint8",
        count=4,
        nodata=None,
        compress="lzw",
        tiled=True,
        photometric="rgb",
    )
    with rasterio.open(OUT_TIF, "w", **profile) as dst:
        for i in range(4):
            dst.write(rgba_uint8[..., i], i + 1)
    print(f"  wrote {OUT_TIF} ({OUT_TIF.stat().st_size/1024/1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
