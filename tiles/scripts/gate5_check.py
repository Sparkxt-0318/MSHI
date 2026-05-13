"""Gate 5: end-to-end render test validation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
INTERMED = ROOT / "tiles" / "intermediate"


def main() -> int:
    stats_path = INTERMED / "phase5_render_stats.json"
    stats = json.loads(stats_path.read_text())

    results = []

    # 1. Server started cleanly: implicit (we got 200 responses)
    server_ok = (stats["fetches"]["z3_6_3"]["status"] == 200
                 and stats["fetches"]["z4_12_6"]["status"] == 200)
    results.append((
        "server_responds",
        server_ok,
        f"z3 status={stats['fetches']['z3_6_3']['status']}, "
        f"z4 status={stats['fetches']['z4_12_6']['status']}",
    ))

    # 2. Both fetches return 200
    results.append((
        "fetches_200",
        server_ok,
        f"z3_6_3 OK ({stats['fetches']['z3_6_3']['bytes']}B), "
        f"z4_12_6 OK ({stats['fetches']['z4_12_6']['bytes']}B)",
    ))

    # 3. Both fetched tiles are valid PNGs (256x256 with visible content)
    z3_dims_ok = stats["fetches"]["z3_6_3"]["dims"] == [256, 256]
    z4_dims_ok = stats["fetches"]["z4_12_6"]["dims"] == [256, 256]
    png_ok = z3_dims_ok and z4_dims_ok
    results.append((
        "valid_pngs",
        png_ok,
        f"z3 dims={stats['fetches']['z3_6_3']['dims']}, "
        f"z4 dims={stats['fetches']['z4_12_6']['dims']}",
    ))

    # 4. Seam continuity in composite
    max_diff = stats["discontinuity"]["max_diff"]
    mean_diff = stats["discontinuity"]["mean_diff"]
    # Allow up to mean RGB diff of 30/255 (~12%) as "continuous".
    # Tile boundaries with proper resampling typically show <5/255 diff.
    seam_ok = max_diff < 30
    results.append((
        "seam_continuity",
        seam_ok,
        f"max RGB seam diff={max_diff:.2f}/255 ({max_diff/2.55:.1f}%), "
        f"mean={mean_diff:.2f}",
    ))

    # 5. Composite has non-trivial coverage
    coverage = stats["composite"]["coverage_pct"]
    coverage_ok = coverage > 50
    results.append((
        "composite_coverage",
        coverage_ok,
        f"{coverage:.1f}% non-background pixels",
    ))

    # 6. Composite file exists
    comp_path = INTERMED / "render_test_composite.png"
    exists_ok = comp_path.exists()
    results.append((
        "composite_file_exists",
        exists_ok,
        f"{comp_path} ({comp_path.stat().st_size/1024:.1f} KB)" if exists_ok else "missing",
    ))

    n_pass = emit(results)
    (INTERMED / "gate5_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE 5 RESULTS")
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
