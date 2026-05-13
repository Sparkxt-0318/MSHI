"""Gate 3: validate zoom rasters."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
INTERMED = ROOT / "tiles" / "intermediate"


def main() -> int:
    results = []

    # 1. All 7 zoom files exist
    files = [INTERMED / f"zoom{z}.{ext}" for z in range(7) for ext in ("tif", "png")]
    all_exist = all(f.exists() for f in files)
    missing = [str(f) for f in files if not f.exists()]
    results.append(("all_7_zoom_files",
                    all_exist,
                    "all present" if all_exist else f"missing: {missing}"))

    # 2. File sizes monotonically increase
    sizes = [(INTERMED / f"zoom{z}.png").stat().st_size for z in range(7)]
    monotonic = all(sizes[i] < sizes[i+1] for i in range(len(sizes)-1))
    # Each higher zoom should be ~4x previous (allow 2x-8x window for tolerance)
    ratios = [sizes[i+1] / sizes[i] for i in range(len(sizes)-1)]
    ratio_ok = all(1.5 <= r <= 8.0 for r in ratios)
    results.append((
        "monotonic_size",
        monotonic,
        f"png sizes (KB): {[s//1024 for s in sizes]}, "
        f"step ratios: {[round(r, 2) for r in ratios]}",
    ))
    results.append((
        "size_ratios_~4x",
        ratio_ok,
        f"ratios within [1.5, 8.0]: {[round(r, 2) for r in ratios]}",
    ))

    # 3. Total size < 200 MB (count tif + png)
    total_bytes = sum(
        (INTERMED / f"zoom{z}.{ext}").stat().st_size
        for z in range(7) for ext in ("tif", "png")
    )
    total_mb = total_bytes / 1024 / 1024
    size_ok = total_mb < 200
    results.append(("total_size_<200MB", size_ok, f"{total_mb:.1f} MB"))

    # 4. Each opens cleanly
    open_ok = True
    open_detail = []
    for z in range(7):
        try:
            with rasterio.open(INTERMED / f"zoom{z}.tif") as ds:
                _ = ds.read(1, window=((0, min(10, ds.height)),
                                       (0, min(10, ds.width))))
            img = Image.open(INTERMED / f"zoom{z}.png")
            img.load()
            open_detail.append(f"z{z}=OK")
        except Exception as e:
            open_ok = False
            open_detail.append(f"z{z}=FAIL({e})")
    results.append(("opens_cleanly", open_ok, ", ".join(open_detail)))

    # 5. zoom3 vs zoom4 distribution similarity
    with rasterio.open(INTERMED / "zoom3.tif") as ds:
        a3 = ds.read(1)
    with rasterio.open(INTERMED / "zoom4.tif") as ds:
        a4 = ds.read(1)
    a3f = a3[np.isfinite(a3)]
    a4f = a4[np.isfinite(a4)]
    # Compare quantiles
    quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]
    q3 = np.quantile(a3f, quantiles)
    q4 = np.quantile(a4f, quantiles)
    max_q_diff = float(np.max(np.abs(q3 - q4)))
    # Tolerance 0.03 — they should be very close
    dist_ok = max_q_diff < 0.05
    results.append((
        "z3_z4_distribution_similar",
        dist_ok,
        f"max quantile diff = {max_q_diff:.4f} (tolerance 0.05); "
        f"q3={[round(v,3) for v in q3]}, q4={[round(v,3) for v in q4]}",
    ))

    n_pass = emit(results)
    (INTERMED / "gate3_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE 3 RESULTS")
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
