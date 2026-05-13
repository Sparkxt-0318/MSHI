"""IGBP-fallback Step 2 — regenerate the real training and validation
feature tables.

Why: the git-tracked training_features.parquet on this branch is the
synthetic demo output (3000 rows, source='synthetic'). The real
respiration_points.parquet is intact, and all SoilGrids / WorldClim
rasters are present on disk — but the four MODIS rasters under
data/raw/modis/ are mostly 2-byte placeholders. Only landcover_igbp_2023.tif
is real (455 KB, EPSG:4326, IGBP codes 1-17).

This script samples 16 real rasters (8 SoilGrids 5-15cm + 8 WorldClim
bioclim) plus the real landcover at every Asia and US site in
respiration_points.parquet, applies SoilGrids unit conversions and
the engineered features, and writes:

    data/processed/training_features.parquet      (Asia, n=615)
    data/processed/us_validation_features.parquet (CONUS, n=274)

The placeholder npp / lst_day / lst_night TIFFs are skipped (filtered
by file size > 1 KB) — those columns will simply be absent.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features import (  # noqa: E402
    add_engineered_features,
    default_registry,
    extract_at_points,
    rescale_soilgrids,
)

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"


def filter_real_rasters(reg: dict) -> dict:
    """Keep only files that exist AND are larger than 1 KB (filters
    out the 2-byte CRLF placeholder TIFFs on this branch)."""
    out = {}
    for k, p in reg.items():
        p = Path(p)
        if p.exists() and p.stat().st_size > 1024:
            out[k] = p
        else:
            print(f"  skipping (placeholder or missing): {k}  -> {p}")
    return out


def extract_for_region(points, region):
    reg = filter_real_rasters(default_registry(RAW, region=region))
    print(f"[{region}] sampling n={len(points)} points × {len(reg)} rasters")
    out = extract_at_points(points, reg)
    out = rescale_soilgrids(out)
    out = add_engineered_features(out)
    if "lst_day" in out.columns and "lst_night" in out.columns:
        out["lst_diurnal_range"] = out["lst_day"] - out["lst_night"]
    return out


def main():
    pts = pd.read_parquet(PROC / "respiration_points.parquet")
    print(f"respiration_points.parquet: {pts.shape}")
    print(f"region distribution: {pts['region'].value_counts().to_dict()}")

    asia = pts[pts["region"] == "asia"].reset_index(drop=True)
    us = pts[pts["region"] == "us"].reset_index(drop=True)

    print(f"\nExtracting Asia training set ({len(asia)} points)...")
    asia_feat = extract_for_region(asia, region="asia")
    print(f"\nExtracting US validation set ({len(us)} points)...")
    us_feat = extract_for_region(us, region="us")

    asia_path = PROC / "training_features.parquet"
    us_path = PROC / "us_validation_features.parquet"
    asia_feat.to_parquet(asia_path, index=False)
    us_feat.to_parquet(us_path, index=False)
    print(f"\nWrote {asia_path}  shape={asia_feat.shape}")
    print(f"Wrote {us_path}  shape={us_feat.shape}")

    # Coverage by feature
    print("\nFeature non-null counts (Asia):")
    feat_cols = [c for c in asia_feat.columns if c not in
                 {"site_id", "source", "region", "longitude", "latitude",
                  "rs_annual", "log_rs_annual"}]
    for c in feat_cols:
        n_ok = asia_feat[c].notna().sum()
        print(f"  {c:<22} {n_ok:>4d}/{len(asia_feat)}  "
              f"({100*n_ok/len(asia_feat):.1f}%)")

    # Landcover class breakdown
    if "landcover" in asia_feat.columns:
        print("\nIGBP class counts (Asia):")
        a = asia_feat["landcover"].dropna().astype(int).value_counts().sort_index()
        for c, n in a.items():
            print(f"  IGBP {c:>2d}: {n}")
        print("\nIGBP class counts (US):")
        u = us_feat["landcover"].dropna().astype(int).value_counts().sort_index()
        for c, n in u.items():
            print(f"  IGBP {c:>2d}: {n}")


if __name__ == "__main__":
    main()
