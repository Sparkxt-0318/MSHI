"""Phase A1 — verify SoilGrids feature units in the training table.

For each SoilGrids variable, print:
  • Post-rescale percentiles from data/processed/training_features.parquet
  • Raw integer percentiles re-sampled directly from the SoilGrids tile at
    the SAME training-point coordinates (no rescaling) — this shows what
    factor must be applied to get the post-rescale value.

This gives us ground truth on whether the rescale_soilgrids() conversion in
src/features.py is correct.
"""
import numpy as np
import pandas as pd
import rasterio
from pathlib import Path

ROOT = Path("/home/user/MSHI")
SG = ROOT / "data" / "raw" / "soilgrids"
TRAIN = ROOT / "data" / "processed" / "training_features.parquet"

VARS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]

df = pd.read_parquet(TRAIN)
print(f"Loaded {len(df)} Asia training points\n")
print("=" * 96)
print("PHASE A1 — soil-feature percentiles in the training table (post-rescale)")
print("=" * 96)
header = f"{'feature':<10s} {'min':>10s} {'p25':>10s} {'p50':>10s} {'p75':>10s} {'max':>10s} {'n_nan':>8s}"
print(header)
print("-" * len(header))
for v in VARS:
    s = df[v].dropna()
    n_nan = df[v].isna().sum()
    if len(s) == 0:
        print(f"{v:<10s}   ALL NAN")
        continue
    print(f"{v:<10s} {s.min():10.3f} {s.quantile(0.25):10.3f} {s.median():10.3f} "
          f"{s.quantile(0.75):10.3f} {s.max():10.3f} {n_nan:>8d}")

# Also: do clay+sand+silt sum to ~100 (if %) or ~1000 (if g/kg)?
texture_sum = df[["clay", "sand", "silt"]].sum(axis=1).dropna()
print(f"\nclay + sand + silt   : median {texture_sum.median():.1f}  "
      f"p5 {texture_sum.quantile(0.05):.1f}  p95 {texture_sum.quantile(0.95):.1f}  "
      f"  (expect ~100 if % units, ~1000 if g/kg units)")

print("\n" + "=" * 96)
print("RAW integer percentiles (sampled directly from the SoilGrids tile, no rescale)")
print("This tells us the multiplier needed to get post-rescale values from raw.")
print("=" * 96)
print(header.replace("n_nan", "n_zero"))
print("-" * len(header))

lons = df["longitude"].to_numpy()
lats = df["latitude"].to_numpy()
coords = list(zip(lons, lats))
for v in VARS:
    p = SG / f"{v}_5-15cm_asia_5km.tif"
    with rasterio.open(p) as src:
        raw = np.array([row[0] for row in src.sample(coords)], dtype="float64")
    valid = raw[raw > 0]  # 0 is nodata convention
    if len(valid) == 0:
        print(f"{v:<10s}  ALL ZERO")
        continue
    n_zero = int((raw == 0).sum())
    print(f"{v:<10s} {valid.min():10.0f} {np.quantile(valid, .25):10.0f} "
          f"{np.median(valid):10.0f} {np.quantile(valid, .75):10.0f} "
          f"{valid.max():10.0f} {n_zero:>8d}")

# What conversion factor was applied? Compare median(rescaled) / median(raw)
print("\n" + "=" * 96)
print("Effective conversion factor (median of rescaled / median of raw)")
print("This is the multiplier currently in src/features.py:SOILGRIDS_SCALE")
print("=" * 96)
print(f"{'feature':<10s} {'median_raw':>12s} {'median_post':>14s} {'effective_factor':>20s}")
for v in VARS:
    p = SG / f"{v}_5-15cm_asia_5km.tif"
    with rasterio.open(p) as src:
        raw = np.array([row[0] for row in src.sample(coords)], dtype="float64")
    valid = raw[raw > 0]
    if len(valid) == 0:
        continue
    med_raw = float(np.median(valid))
    med_post = float(df[v].dropna().median())
    factor = med_post / med_raw if med_raw else float("nan")
    print(f"{v:<10s} {med_raw:>12.1f} {med_post:>14.3f} {factor:>20.5f}")

# Reference ranges from common references (Hengl et al. 2017, ISRIC FAQ)
print("\n" + "=" * 96)
print("Reference ranges for sanity check (typical mineral soil, 5-15cm)")
print("=" * 96)
print("  soc       : 5-80 g/kg          (organic soils up to ~300)")
print("  nitrogen  : 0.5-6 g/kg")
print("  phh2o     : 4-9 (pH)")
print("  clay      : 50-500 g/kg  =  5-50%")
print("  sand      : 100-800 g/kg = 10-80%")
print("  silt      : 100-700 g/kg = 10-70%")
print("  clay+sand+silt: ~1000 g/kg  =  ~100%")
print("  bdod      : 0.9-1.8 g/cm3")
print("  cec       : 5-50 cmol(c)/kg")
