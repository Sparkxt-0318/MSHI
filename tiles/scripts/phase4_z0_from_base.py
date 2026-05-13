"""
Render Z0 (whole-world) tile directly from the base raster and inject
into the MBTiles. This replaces the previous approach of downsampling
Z1 → Z0, which loses fidelity at the global view.

Z0 is the single tile (0, 0, 0) of the web-mercator pyramid: a
256x256 PNG covering the whole world from lon -180..180 and lat
-85.05..85.05 (mercator clip). Our data covers lon 25..180 and lat
-10..80, so only a portion of the Z0 tile will be populated.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"
MBT = ROOT / "tiles" / "intermediate" / "mshi.mbtiles"

VMIN, VMAX = 0.5, 1.5
TILE_SIZE = 256

# Web mercator bounds (EPSG:3857)
WEB_MERC_MAX = 20037508.3427892
WEB_MERC_MIN = -WEB_MERC_MAX


def main() -> int:
    # Reproject base raster to EPSG:3857 covering the WHOLE WORLD bbox,
    # at a resolution where one pixel = ~1/256 of the world.
    # Z0 tile is 256x256 for the whole world, so target resolution =
    # 2 * WEB_MERC_MAX / 256 = ~156543 m/px.
    print("Phase 4 Z0: rendering whole-world Z0 tile from base raster...")
    with rasterio.open(BASE_TIF) as src:
        # Build a fresh target raster at world-bbox in EPSG:3857
        target_res = 2 * WEB_MERC_MAX / TILE_SIZE
        # Target raster covers world but only Asia rows/cols will be filled.
        from rasterio.transform import Affine
        dst_transform = Affine(target_res, 0, WEB_MERC_MIN,
                                0, -target_res, WEB_MERC_MAX)
        dst_arr = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:3857",
            resampling=Resampling.average,
        )

    # Apply RdBu cmap (red=low/suppressed, blue=high — hero-aligned)
    cmap = plt.get_cmap("RdBu").resampled(4096)
    norm = Normalize(vmin=VMIN, vmax=VMAX)
    rgba = cmap(norm(dst_arr))
    mask = ~np.isfinite(dst_arr)
    rgba[..., 3] = np.where(mask, 0.0, 1.0)
    rgba_uint8 = (rgba * 255).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(rgba_uint8, mode="RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    z0_data = buf.getvalue()
    print(f"  Z0 tile: {len(z0_data)} bytes")

    # Insert into MBTiles
    conn = sqlite3.connect(MBT)
    cur = conn.cursor()
    cur.execute("DELETE FROM tiles WHERE zoom_level=0")
    cur.execute(
        "INSERT INTO tiles (zoom_level, tile_column, tile_row, tile_data) "
        "VALUES (?, ?, ?, ?)",
        (0, 0, 0, z0_data),
    )
    cur.execute("UPDATE metadata SET value='0' WHERE name='minzoom'")
    cur.execute("UPDATE metadata SET value='6' WHERE name='maxzoom'")
    conn.commit()

    # Verify
    for row in cur.execute("SELECT zoom_level, COUNT(*) FROM tiles "
                            "GROUP BY zoom_level ORDER BY zoom_level"):
        print(f"  {row}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
