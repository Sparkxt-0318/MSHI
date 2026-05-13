"""
Gates B + D: viewer.html static analysis.

Gate B: globe projection enabled, MapLibre >= 5.0
Gate D: legend updated (no 'synthetic' string, real-data label present)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEWER = ROOT / "tiles" / "viewer.html"


def main() -> int:
    results = []

    if not VIEWER.exists():
        results.append(("viewer_exists", False, str(VIEWER)))
        emit(results)
        return 1

    src = VIEWER.read_text()

    # Gate B
    has_globe = bool(re.search(r"projection\s*:\s*\{[^}]*type:\s*['\"]globe['\"]", src)
                     or "projection: 'globe'" in src
                     or 'projection: "globe"' in src)
    results.append((
        "B_projection_globe",
        has_globe,
        f"projection:'globe' present: {has_globe}",
    ))

    # MapLibre version >= 5
    ml_match = re.search(r"maplibre-gl@(\d+)\.(\d+)\.(\d+)", src)
    if ml_match:
        major = int(ml_match.group(1))
        ml_ver = f"{major}.{ml_match.group(2)}.{ml_match.group(3)}"
        ml_ok = major >= 5
    else:
        ml_ver = "not found"
        ml_ok = False
    results.append(("B_maplibre_>=5", ml_ok, f"MapLibre version: {ml_ver}"))

    # Gate D — legend
    has_synthetic = re.search(r"\bsynthetic\b", src, re.IGNORECASE) is not None
    results.append((
        "D_no_synthetic_string",
        not has_synthetic,
        f"'synthetic' present in source: {has_synthetic}",
    ))

    has_real_label = (
        "real" in src.lower()
        or "n=615" in src
        or "F+NPP" in src
        or "f+npp" in src.lower()
        or "SRDB" in src or "srdb" in src.lower()
    )
    results.append((
        "D_real_data_label",
        has_real_label,
        f"real-data label present: {has_real_label} "
        f"(checks: 'real', 'n=615', 'F+NPP', 'SRDB')",
    ))

    n_pass = emit(results)
    (ROOT / "tiles" / "intermediate" / "gateBD_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATES B + D RESULTS (viewer.html static)")
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
