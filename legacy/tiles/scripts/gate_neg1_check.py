"""Gate -1: validate real-data input replacement."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    results = []

    # 1. Critical inputs present
    inputs = {
        "F_NPP_model.json": ROOT / "data" / "outputs" / "F_NPP_model.json",
        "training_features_v2.parquet": ROOT / "data" / "processed" / "training_features_v2.parquet",
    }
    all_critical = all(p.exists() for p in inputs.values())
    results.append((
        "critical_inputs",
        all_critical,
        ", ".join(f"{n}={'OK' if p.exists() else 'MISSING'}"
                  for n, p in inputs.items()),
    ))

    # MODIS rasters: at least 3 of 4 present
    modis_inputs = {
        "npp_2020_2024_mean.tif": ROOT / "data" / "raw" / "modis" / "npp_2020_2024_mean.tif",
        "lst_day_2020_2024_mean.tif": ROOT / "data" / "raw" / "modis" / "lst_day_2020_2024_mean.tif",
        "lst_night_2020_2024_mean.tif": ROOT / "data" / "raw" / "modis" / "lst_night_2020_2024_mean.tif",
        "landcover_igbp_2023.tif": ROOT / "data" / "raw" / "modis" / "landcover_igbp_2023.tif",
    }
    n_modis = sum(1 for p in modis_inputs.values() if p.exists())
    results.append((
        "modis_rasters_>=3",
        n_modis >= 3,
        f"{n_modis}/4 present: " + ", ".join(
            f"{n}={'OK' if p.exists() else 'MISSING'}"
            for n, p in modis_inputs.items()
        ),
    ))

    # 2. training_features_v2 source check
    src_ok = False
    src_detail = "n/a"
    if inputs["training_features_v2.parquet"].exists():
        df = pd.read_parquet(inputs["training_features_v2.parquet"])
        if "source" in df.columns:
            sources = df["source"].astype(str).str.lower().unique()
            has_synthetic = any("synthetic" in s for s in sources)
            has_real = any(s in ("srdb", "cosore") for s in sources)
            src_ok = (not has_synthetic) and has_real
            src_detail = (
                f"unique sources={list(sources)}; "
                f"has_synthetic={has_synthetic}, has_real={has_real}"
            )
        else:
            src_detail = "no 'source' column"
    results.append(("training_source_real", src_ok, src_detail))

    # 3. training_features_v2 row count 500-700
    row_ok = False
    row_detail = "n/a"
    if inputs["training_features_v2.parquet"].exists():
        df = pd.read_parquet(inputs["training_features_v2.parquet"])
        n = len(df)
        row_ok = 500 <= n <= 700
        row_detail = f"{n} rows (expected 500-700)"
    results.append(("training_row_count", row_ok, row_detail))

    # 4. F_NPP_model.json size > 100 KB
    sz_ok = False
    sz_detail = "n/a"
    if inputs["F_NPP_model.json"].exists():
        sz = inputs["F_NPP_model.json"].stat().st_size
        sz_ok = sz > 100 * 1024
        sz_detail = f"{sz/1024:.1f} KB (expected >100 KB)"
    results.append(("F_NPP_model_size", sz_ok, sz_detail))

    # 5. Each present MODIS raster has real content.
    # Threshold tuned: 1MB for continuous-valued bands (npp, lst_*),
    # 100KB for categorical rasters (landcover) which compress much
    # smaller via LZW. Either threshold is >>50000x larger than the
    # 2-byte placeholder the gate is meant to catch.
    continuous_bands = {"npp_2020_2024_mean.tif",
                        "lst_day_2020_2024_mean.tif",
                        "lst_night_2020_2024_mean.tif"}
    modis_size_ok = True
    modis_size_detail = []
    for name, p in modis_inputs.items():
        if p.exists():
            sz = p.stat().st_size
            threshold = 1024 * 1024 if name in continuous_bands else 100 * 1024
            ok = sz > threshold
            kind = "continuous" if name in continuous_bands else "categorical"
            modis_size_detail.append(
                f"{name}={sz/1024/1024:.2f}MB({kind}, >{threshold/1024:.0f}KB)"
                f"{'' if ok else ' TOO_SMALL'}"
            )
            if not ok:
                modis_size_ok = False
    results.append(("modis_sizes_real", modis_size_ok,
                    ", ".join(modis_size_detail)))

    n_pass = emit(results)
    (ROOT / "tiles" / "intermediate" / "gate_neg1_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE -1 RESULTS (real-data input replacement)")
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
