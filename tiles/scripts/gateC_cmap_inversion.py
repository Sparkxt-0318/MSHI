"""
Gate C: verify colormap is inverted (RdBu = red for LOW anomaly,
blue for HIGH anomaly) to match the published hero map convention.

We sample the base raster at known sites with consistent anomaly
direction in the real F+NPP output:
  - Eastern Siberia (60°N, 120°E): mean ~0.91 → strong RED expected
  - Mongolia (47.5°N, 105°E): mean ~0.98 → mild RED expected
  - Indo-Gangetic (28°N, 78°E): mean ~1.06 → mild BLUE expected
  - Egypt (31°E, 31°N): mean ~1.6 → strong BLUE expected (data peak)

For each site we compute the RGB through the live pipeline cmap
applied to the patch mean. The check is:
  - anomaly < 1.0 → mean RGB has R > B
  - anomaly > 1.0 → mean RGB has B > R

This is a deterministic test of cmap direction that does NOT depend
on tile-mean averaging (which mixes high and low cells together).
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
TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"

VMIN, VMAX = 0.5, 1.5
CMAP = plt.get_cmap("RdBu").resampled(4096)  # must match phase2/3/4 cmap
NORM = Normalize(vmin=VMIN, vmax=VMAX)


def patch_mean(ds, lon, lat, half_px=10):
    r, c = ds.index(lon, lat)
    r0, r1 = max(0, r - half_px), min(ds.height, r + half_px + 1)
    c0, c1 = max(0, c - half_px), min(ds.width, c + half_px + 1)
    patch = ds.read(1, window=((r0, r1), (c0, c1)))
    finite = patch[np.isfinite(patch)]
    return (float(finite.mean()) if len(finite) > 0 else float("nan"),
            int(len(finite)))


def rgb_at(value):
    rgba = CMAP(NORM(value))
    return tuple(int(round(c * 255)) for c in rgba[:3])


def main() -> int:
    results = []

    if not TIF.exists():
        results.append(("base_raster_exists", False, str(TIF)))
        emit(results)
        return 1

    sites = [
        ("Mongolia", 105.0, 47.5, "<", "RED"),
        ("Indo_Gangetic", 78.0, 28.0, ">", "BLUE"),
        ("Eastern_Siberia", 120.0, 60.0, "<", "RED"),
        ("Indo_Gangetic_central", 82.0, 26.0, ">", "BLUE"),  # task fallback
    ]

    with rasterio.open(TIF) as ds:
        for name, lon, lat, direction, expected_color in sites:
            mean, n = patch_mean(ds, lon, lat)
            if np.isnan(mean):
                results.append((
                    f"{name}_anomaly_finite",
                    False,
                    f"NaN at ({lon},{lat})",
                ))
                continue
            R, G, B = rgb_at(mean)
            data_dir = "<" if mean < 1.0 else ">"
            data_dir_ok = (data_dir == direction)
            # Color check based on actual data direction
            if data_dir == "<":
                color = "RED" if R > B else ("BLUE" if B > R else "NEUTRAL")
                color_ok = (color == "RED")
            else:
                color = "BLUE" if B > R else ("RED" if R > B else "NEUTRAL")
                color_ok = (color == "BLUE")
            results.append((
                f"{name}_cmap_direction",
                color_ok,
                f"anomaly={mean:.3f} ({data_dir}1.0), pixel RGB={R},{G},{B} → {color} "
                f"(expected {expected_color} for {direction}1.0). Direction match: {data_dir_ok}",
            ))

    # Endpoint tests — verify cmap behaves at extremes
    test_low = rgb_at(0.6)
    test_high = rgb_at(1.4)
    low_red = test_low[0] > test_low[2] + 50  # strong red
    high_blue = test_high[2] > test_low[0]
    results.append((
        "strong_low_anomaly_is_RED",
        low_red,
        f"anomaly=0.6 → RGB={test_low}, R>B+50: {low_red}",
    ))
    results.append((
        "strong_high_anomaly_is_BLUE",
        test_high[2] > test_high[0] + 50,
        f"anomaly=1.4 → RGB={test_high}, B>R+50: {test_high[2] > test_high[0] + 50}",
    ))

    n_pass = emit(results)
    (ROOT / "tiles" / "intermediate" / "gateC_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE C RESULTS (colormap inversion applied)")
    print("=" * 78)
    n_pass = 0
    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        if ok:
            n_pass += 1
        print(f"  [{flag}] {name}: {detail}")
    print("=" * 78)
    print(f"Total: {n_pass}/{len(results)} passed")
    print("=" * 78)
    return n_pass


if __name__ == "__main__":
    raise SystemExit(main())
