"""Gate 1: validate base raster."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[2]
TIF = ROOT / "tiles" / "intermediate" / "asia_anomaly_base.tif"


def main() -> int:
    results = []

    # 1. File exists
    results.append(("exists", TIF.exists(), str(TIF)))
    if not TIF.exists():
        emit(results)
        return 1

    # 2. CRS
    with rasterio.open(TIF) as ds:
        crs = str(ds.crs)
        dtype = ds.dtypes[0]
        w, h = ds.width, ds.height
        nodata = ds.nodata
        # 6. test pixel reads
        # lon=105, lat=45 (Mongolia)
        row45_105 = int((45.0 - ds.transform.f) / -ds.transform.e) - 0  # row from top
        # Use rasterio's index function
        r1, c1 = ds.index(105.0, 45.0)
        v1 = ds.read(1, window=((r1, r1 + 1), (c1, c1 + 1)))[0, 0]

        r2, c2 = ds.index(70.0, -5.0)  # Indian Ocean
        v2 = ds.read(1, window=((r2, r2 + 1), (c2, c2 + 1)))[0, 0]

        # Stats
        arr = ds.read(1)
        finite = np.isfinite(arr)
        n_finite = int(finite.sum())
        if n_finite == 0:
            stats = {"min": float("nan"), "max": float("nan"), "mean": float("nan")}
        else:
            stats = {
                "min": float(np.nanmin(arr)),
                "max": float(np.nanmax(arr)),
                "mean": float(np.nanmean(arr)),
            }

    results.append((
        "crs_4326",
        "EPSG:4326" in crs.upper() or crs.upper().endswith("4326"),
        crs,
    ))
    results.append(("dtype_float32", dtype == "float32", dtype))
    width_ok = (3000 - 100) <= w <= (3000 + 100)
    height_ok = (1800 - 100) <= h <= (1800 + 100)
    results.append((
        "dimensions",
        width_ok and height_ok,
        f"{w} x {h} (W x H), expected ~3000±100 x 1800±100",
    ))
    # 5. value stats
    stats_ok = (
        0.3 <= stats["min"] <= 2.0
        and 0.3 <= stats["max"] <= 2.0
        and 0.8 <= stats["mean"] <= 1.2
    )
    results.append((
        "value_stats",
        stats_ok,
        f"min={stats['min']:.3f} max={stats['max']:.3f} mean={stats['mean']:.3f}",
    ))
    # 6. Mongolia pixel finite
    mong_ok = bool(np.isfinite(v1))
    results.append((
        "mongolia_pixel_finite",
        mong_ok,
        f"lon=105 lat=45 value={float(v1):.4f}",
    ))
    # 7. Indian Ocean pixel NaN
    ocean_ok = not bool(np.isfinite(v2))
    results.append((
        "indian_ocean_pixel_nan",
        ocean_ok,
        f"lon=70 lat=-5 value={float(v2):.4f}",
    ))

    n_pass = emit(results)
    (ROOT / "tiles" / "intermediate" / "gate1_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE 1 RESULTS")
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
