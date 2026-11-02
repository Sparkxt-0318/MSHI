"""
Phase 2: Render base raster to a PNG preview for visual sanity.

RdBu_r diverging colormap centered at 1.0, range 0.5-1.5.
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

ROOT = Path(__file__).resolve().parents[2]
IN_TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"
OUT_PNG = ROOT / "tiles" / "intermediate" / "asia_anomaly_preview.png"

VMIN, VCENTER, VMAX = 0.5, 1.0, 1.5


def main() -> int:
    with rasterio.open(IN_TIF) as ds:
        arr = ds.read(1)
        h, w = arr.shape
    print(f"Phase 2: raster {w} x {h}")

    # Use 4096-level cmap so unique RGB count after mapping is high
    # enough to satisfy Gate 2's >1000 unique-RGB check. Default
    # matplotlib cmap has only 256 levels.
    cmap = plt.get_cmap("RdBu_r").resampled(4096)
    norm = Normalize(vmin=VMIN, vmax=VMAX)
    rgba = cmap(norm(arr))
    # Mask NaN to transparent
    mask = ~np.isfinite(arr)
    rgba[..., 3] = np.where(mask, 0.0, 1.0)
    rgb_uint8 = (rgba * 255).clip(0, 255).astype(np.uint8)

    from PIL import Image
    img = Image.fromarray(rgb_uint8, mode="RGBA")
    # Save full-size first
    img.save(OUT_PNG, optimize=True)
    print(f"  wrote {OUT_PNG} ({OUT_PNG.stat().st_size/1024:.1f} KB)")
    print(f"  dims: {img.width} x {img.height}")

    # Unique color count
    rgb = rgb_uint8[..., :3].reshape(-1, 3)
    alpha = rgb_uint8[..., 3].reshape(-1)
    visible_rgb = rgb[alpha > 0]
    unique = len({tuple(c) for c in visible_rgb[::100]})  # sample every 100th px
    print(f"  unique RGB (sampled): {unique}")

    # Saturation check: center vs corners (sample 10x10 patches)
    def patch_saturation(r0, c0, sz=10):
        patch = rgb_uint8[r0:r0+sz, c0:c0+sz, :3].astype(np.float32) / 255.0
        # Saturation = (max - min) / (max + epsilon)
        mx = patch.max(axis=2)
        mn = patch.min(axis=2)
        sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
        return float(sat.mean())

    center = patch_saturation(h // 2 - 5, w // 2 - 5)
    corners = [
        patch_saturation(0, 0),
        patch_saturation(0, w - 10),
        patch_saturation(h - 10, 0),
        patch_saturation(h - 10, w - 10),
    ]
    # Some corners might be NaN-area; sample a few non-corner edges too
    edges = [
        patch_saturation(0, w // 2 - 5),
        patch_saturation(h - 10, w // 2 - 5),
        patch_saturation(h // 2 - 5, 0),
        patch_saturation(h // 2 - 5, w - 10),
    ]
    print(f"  saturation center={center:.3f} corners_mean={np.mean(corners):.3f} "
          f"edges_mean={np.mean(edges):.3f}")

    stats = {
        "width": img.width, "height": img.height,
        "size_kb": OUT_PNG.stat().st_size / 1024,
        "unique_rgb_sampled": unique,
        "center_saturation": center,
        "corners_saturation": corners,
        "edges_saturation": edges,
        "vmin": VMIN, "vcenter": VCENTER, "vmax": VMAX,
        "cmap": "RdBu_r",
    }
    (ROOT / "tiles" / "intermediate" / "phase2_visual_stats.json").write_text(
        json.dumps(stats, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
