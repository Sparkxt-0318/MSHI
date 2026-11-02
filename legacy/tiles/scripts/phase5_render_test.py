"""
Phase 5: End-to-end render test via local pmtiles serve.

1. Server already running at localhost:8765
2. Fetch z=3 (x=6, y=3) and z=4 (x=12, y=6) — these are spatially
   overlapping (deeper zoom shows 1/4 of the parent tile area)
3. Stitch 3x3 grid of z=3 tiles around the central Asia region into
   render_test_composite.png
4. Compute boundary discontinuity along tile seams
"""

from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
INTERMED = ROOT / "tiles" / "intermediate"
OUT_COMPOSITE = INTERMED / "render_test_composite.png"

BASE_URL = "http://localhost:8765/mshi_f_npp_anomaly"


def fetch(z: int, x: int, y: int) -> tuple[int, bytes]:
    url = f"{BASE_URL}/{z}/{x}/{y}.png"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


def main() -> int:
    out = {"fetches": {}, "composite": {}, "discontinuity": {}}

    # 1. Fetch z=3 (6, 3)
    print("Fetching z=3 (6, 3)...")
    status3, data3 = fetch(3, 6, 3)
    out["fetches"]["z3_6_3"] = {"status": status3, "bytes": len(data3)}
    print(f"  status={status3} bytes={len(data3)}")

    # 2. Fetch z=4 (12, 6) — directly below (6,3) in pyramid
    print("Fetching z=4 (12, 6)...")
    status4, data4 = fetch(4, 12, 6)
    out["fetches"]["z4_12_6"] = {"status": status4, "bytes": len(data4)}
    print(f"  status={status4} bytes={len(data4)}")

    # Save fetched tiles
    (INTERMED / "render_test_z3_6_3.png").write_bytes(data3)
    (INTERMED / "render_test_z4_12_6.png").write_bytes(data4)

    # Validate PNGs
    img3 = Image.open(io.BytesIO(data3)).convert("RGBA")
    img4 = Image.open(io.BytesIO(data4)).convert("RGBA")
    a3 = np.array(img3)
    a4 = np.array(img4)
    out["fetches"]["z3_6_3"]["dims"] = img3.size
    out["fetches"]["z3_6_3"]["visible_px"] = int((a3[..., 3] > 0).sum())
    out["fetches"]["z4_12_6"]["dims"] = img4.size
    out["fetches"]["z4_12_6"]["visible_px"] = int((a4[..., 3] > 0).sum())
    print(f"  z3 dims={img3.size} visible={out['fetches']['z3_6_3']['visible_px']}")
    print(f"  z4 dims={img4.size} visible={out['fetches']['z4_12_6']['visible_px']}")

    # 3. Stitch 3x3 grid of z=3 tiles centered at (6, 3)
    print("Stitching 3x3 z=3 composite around (6, 3)...")
    composite = Image.new("RGBA", (256 * 3, 256 * 3), (255, 255, 255, 255))
    tile_arrs = {}
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x, y = 6 + dx, 3 + dy
            status, data = fetch(3, x, y)
            if status == 200 and data:
                tile_img = Image.open(io.BytesIO(data)).convert("RGBA")
                composite.paste(tile_img, ((dx + 1) * 256, (dy + 1) * 256))
                tile_arrs[(x, y)] = np.array(tile_img)
            else:
                print(f"  WARN: z3 ({x},{y}) status={status}")
    composite.save(OUT_COMPOSITE)
    print(f"  wrote {OUT_COMPOSITE} ({OUT_COMPOSITE.stat().st_size/1024:.1f} KB)")

    # 4. Boundary discontinuity check
    # For each horizontal seam between vertically-adjacent tiles, compare
    # the bottom row of upper tile with the top row of lower tile.
    # Large mean RGB diff = bad. Small mean RGB diff = continuous.
    discontinuities = []
    for dx in (-1, 0, 1):
        x = 6 + dx
        for dy_pair in [(-1, 0), (0, 1)]:
            up = tile_arrs.get((x, 3 + dy_pair[0]))
            dn = tile_arrs.get((x, 3 + dy_pair[1]))
            if up is None or dn is None:
                continue
            bottom_up = up[-1, :, :3].astype(np.float32)
            top_dn = dn[0, :, :3].astype(np.float32)
            # Mask to where both are visible
            mask = (up[-1, :, 3] > 0) & (dn[0, :, 3] > 0)
            if mask.sum() < 10:
                continue
            diff = np.abs(bottom_up[mask] - top_dn[mask]).mean()
            discontinuities.append({
                "type": "horizontal_seam_below_x={}".format(x),
                "between_y": list(dy_pair),
                "mean_rgb_diff": float(diff),
                "n_compared_px": int(mask.sum()),
            })
    # Same for vertical seams
    for dy in (-1, 0, 1):
        y = 3 + dy
        for dx_pair in [(-1, 0), (0, 1)]:
            lt = tile_arrs.get((6 + dx_pair[0], y))
            rt = tile_arrs.get((6 + dx_pair[1], y))
            if lt is None or rt is None:
                continue
            right_lt = lt[:, -1, :3].astype(np.float32)
            left_rt = rt[:, 0, :3].astype(np.float32)
            mask = (lt[:, -1, 3] > 0) & (rt[:, 0, 3] > 0)
            if mask.sum() < 10:
                continue
            diff = np.abs(right_lt[mask] - left_rt[mask]).mean()
            discontinuities.append({
                "type": "vertical_seam_right_of_y={}".format(y),
                "between_x": list(dx_pair),
                "mean_rgb_diff": float(diff),
                "n_compared_px": int(mask.sum()),
            })

    # Reference: in-tile diff between adjacent pixel rows. If the data
    # naturally has high spatial variance (real-data case), the seam
    # diff should still be close to the in-tile diff at adjacent pixels.
    # If seam diff >> in-tile diff, that's a pipeline issue. If they're
    # comparable, the seam is as continuous as the data is.
    in_tile_diffs = []
    for (x, y), arr in tile_arrs.items():
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3]
        # Row-to-row diffs of adjacent visible pixels
        m_v = (alpha[:-1, :] > 0) & (alpha[1:, :] > 0)
        if m_v.sum() > 100:
            d_v = np.abs(rgb[:-1, :, :] - rgb[1:, :, :]).mean(axis=2)
            in_tile_diffs.append(float(d_v[m_v].mean()))
        m_h = (alpha[:, :-1] > 0) & (alpha[:, 1:] > 0)
        if m_h.sum() > 100:
            d_h = np.abs(rgb[:, :-1, :] - rgb[:, 1:, :]).mean(axis=2)
            in_tile_diffs.append(float(d_h[m_h].mean()))
    in_tile_mean = float(np.mean(in_tile_diffs)) if in_tile_diffs else 0.0

    out["discontinuity"] = {
        "seams": discontinuities,
        "max_diff": (max(d["mean_rgb_diff"] for d in discontinuities)
                     if discontinuities else 0),
        "mean_diff": (np.mean([d["mean_rgb_diff"] for d in discontinuities])
                      if discontinuities else 0),
        "in_tile_mean_diff": in_tile_mean,
        "seam_to_in_tile_ratio": (
            np.mean([d["mean_rgb_diff"] for d in discontinuities]) / in_tile_mean
            if (discontinuities and in_tile_mean > 0) else 0
        ),
    }
    print(f"  seam discontinuity max={out['discontinuity']['max_diff']:.2f} "
          f"mean={out['discontinuity']['mean_diff']:.2f} "
          f"in-tile-mean={in_tile_mean:.2f} "
          f"ratio={out['discontinuity']['seam_to_in_tile_ratio']:.2f}")

    # Composite coverage
    comp_arr = np.array(composite)
    visible_total = int((comp_arr[..., 3] > 0).sum())
    # but composite was created with white background, so visible_px from
    # composite alpha is always 100%. Better: check non-white pixels.
    # The composite background is white (255,255,255). Tiles paste over it.
    # We pasted with .paste(img, pos) which doesn't preserve alpha; the
    # default behavior preserves the rgba but stays opaque. Let me check.
    # Actually, given we pasted RGBA images onto an opaque canvas, alpha
    # was overridden. We need to compare against transparent tile pixels.
    # Easier: check how many composite pixels are not equal to the white
    # background — that's our coverage.
    nonwhite = ((comp_arr[..., 0] != 255) |
                (comp_arr[..., 1] != 255) |
                (comp_arr[..., 2] != 255)).sum()
    out["composite"] = {
        "dims": composite.size,
        "nonwhite_px": int(nonwhite),
        "total_px": int(comp_arr.shape[0] * comp_arr.shape[1]),
        "coverage_pct": float(nonwhite / (comp_arr.shape[0] * comp_arr.shape[1]) * 100),
    }
    print(f"  composite coverage: {out['composite']['coverage_pct']:.1f}%")

    (INTERMED / "phase5_render_stats.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
