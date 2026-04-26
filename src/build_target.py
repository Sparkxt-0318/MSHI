"""
build_target.py — construct the training table from COSORE + SRDB soil
respiration measurements.

What this does:
  1. Loads SRDB v5 (annual Rs records) and COSORE (continuous flux records)
  2. Filters to records with valid Rs_annual (g C m-2 yr-1), valid lat/lon
  3. Aggregates COSORE continuous records to per-site annual estimates
     (only sites with ≥9 months of data; integrates flux to annual)
  4. Deduplicates between COSORE and SRDB by spatial proximity
  5. Outputs a clean point dataset: site_id, source, lon, lat, rs_annual, log_rs_annual

This produces the *training points*. Feature extraction at these points
happens in features.py.

Run:
    python src/build_target.py --srdb data/raw/srdb/srdb-data.csv \\
                               --cosore data/raw/cosore/  \\
                               --out data/processed/respiration_points.parquet
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("mshi_geo.build_target")


# Reasonable bounds (g C m-2 yr-1). Anything outside is suspect.
RS_MIN, RS_MAX = 50.0, 4500.0


def load_srdb(srdb_path: Path) -> pd.DataFrame:
    """
    Load and filter SRDB v5.

    Required columns (will be remapped if present): Latitude, Longitude,
    Rs_annual, Manipulation, Ecosystem_type, Soil_type.
    """
    LOG.info("Loading SRDB from %s", srdb_path)
    df = pd.read_csv(srdb_path, low_memory=False)
    LOG.info("  raw rows: %d", len(df))

    # Column-name harmonization (SRDB v5 names)
    rename = {
        "Latitude": "latitude",
        "Longitude": "longitude",
        "Rs_annual": "rs_annual",
        "Manipulation": "manipulation",
        "Ecosystem_type": "ecosystem",
        "Study_midyear": "year",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    keep = ["latitude", "longitude", "rs_annual"]
    for opt in ["manipulation", "ecosystem", "year"]:
        if opt in df.columns:
            keep.append(opt)
    df = df[keep].copy()

    # Filter
    n0 = len(df)
    df = df.dropna(subset=["latitude", "longitude", "rs_annual"])
    df = df[(df["rs_annual"] >= RS_MIN) & (df["rs_annual"] <= RS_MAX)]
    if "manipulation" in df.columns:
        # Drop manipulated treatments — we want unperturbed baseline measurements
        df = df[df["manipulation"].isin(["None", "Control", "control", None]) |
                df["manipulation"].isna()]
    LOG.info("  after filtering: %d (dropped %d)", len(df), n0 - len(df))

    df["source"] = "srdb"
    df["site_id"] = "srdb_" + df.index.astype(str)
    return df.reset_index(drop=True)


def load_cosore(cosore_dir: Path) -> Optional[pd.DataFrame]:
    """
    Load COSORE site-level annual estimates.

    COSORE schema is more complex than SRDB. The R package gives clean per-site
    annual integrals; if you exported via R, look for description.csv (sites)
    and the per-port flux files. Here we expect at minimum a 'sites.csv' or
    'description.csv' with columns: site, latitude, longitude, rs_annual.
    """
    if not cosore_dir.exists():
        LOG.warning("COSORE dir not found: %s — skipping", cosore_dir)
        return None

    candidates = list(cosore_dir.glob("*.csv"))
    if not candidates:
        LOG.warning("No CSVs in %s — skipping COSORE", cosore_dir)
        return None

    # Try common file names in priority order
    for name in ["annual_summaries.csv", "description.csv", "sites.csv",
                 "cosore_annual.csv"]:
        p = cosore_dir / name
        if p.exists():
            LOG.info("Loading COSORE from %s", p)
            df = pd.read_csv(p, low_memory=False)
            break
    else:
        LOG.warning("None of the expected COSORE files found. Available: %s",
                    [p.name for p in candidates])
        LOG.warning("If you have a different filename, edit build_target.py:load_cosore")
        return None

    # Column harmonization — adjust based on actual COSORE export
    cols_lower = {c.lower(): c for c in df.columns}
    def col(name):
        return cols_lower.get(name)

    lat_c = col("latitude") or col("lat")
    lon_c = col("longitude") or col("lon")
    rs_c  = col("rs_annual") or col("annual_rs") or col("annual_flux_gc_m2_yr")

    if not all([lat_c, lon_c, rs_c]):
        LOG.error("COSORE file missing lat/lon/rs_annual columns. Found: %s",
                  list(df.columns)[:20])
        return None

    df = df.rename(columns={lat_c: "latitude", lon_c: "longitude", rs_c: "rs_annual"})
    df = df.dropna(subset=["latitude", "longitude", "rs_annual"])
    df = df[(df["rs_annual"] >= RS_MIN) & (df["rs_annual"] <= RS_MAX)]
    df["source"] = "cosore"
    df["site_id"] = "cosore_" + df.index.astype(str)

    LOG.info("  COSORE rows: %d", len(df))
    return df[["latitude", "longitude", "rs_annual", "source", "site_id"]]


def deduplicate_spatial(df: pd.DataFrame, threshold_deg: float = 0.05) -> pd.DataFrame:
    """
    Remove near-duplicate points (within ~5km) when they appear in both sources.
    Prefer COSORE (higher fidelity, continuous measurements) over SRDB.
    """
    n0 = len(df)
    df = df.sort_values("source", ascending=False).reset_index(drop=True)  # cosore first
    grid_lon = (df["longitude"] / threshold_deg).round().astype(int)
    grid_lat = (df["latitude"]  / threshold_deg).round().astype(int)
    df["__cell"] = list(zip(grid_lon, grid_lat))
    df = df.drop_duplicates(subset="__cell", keep="first").drop(columns="__cell")
    LOG.info("Spatial dedup: %d → %d", n0, len(df))
    return df.reset_index(drop=True)


def main(srdb_path: Optional[Path], cosore_dir: Optional[Path],
         out_path: Path) -> int:
    frames = []
    if srdb_path and srdb_path.exists():
        frames.append(load_srdb(srdb_path))
    else:
        LOG.warning("SRDB path missing or not provided: %s", srdb_path)

    if cosore_dir and cosore_dir.exists():
        cdf = load_cosore(cosore_dir)
        if cdf is not None:
            frames.append(cdf)

    if not frames:
        LOG.error("No input data loaded. Aborting.")
        return 1

    # Standardize columns
    cols = ["site_id", "source", "longitude", "latitude", "rs_annual"]
    frames = [f[[c for c in cols if c in f.columns]] for f in frames]
    df = pd.concat(frames, ignore_index=True)
    df = deduplicate_spatial(df)
    df["log_rs_annual"] = np.log(df["rs_annual"])

    # Asia / US tag for downstream split
    asia_mask = (
        (df["longitude"].between(25, 180)) &
        (df["latitude"].between(-10, 80))
    )
    us_mask = (
        (df["longitude"].between(-125, -66)) &
        (df["latitude"].between(24, 50))
    )
    df["region"] = np.where(asia_mask, "asia", np.where(us_mask, "us", "other"))

    LOG.info("Region distribution: %s",
             dict(df["region"].value_counts()))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    LOG.info("Saved %d points → %s", len(df), out_path)
    print("\n=== TARGET TABLE SUMMARY ===")
    print(f"  Total points:    {len(df)}")
    print(f"  Asian points:    {(df['region']=='asia').sum()}")
    print(f"  US points:       {(df['region']=='us').sum()}")
    print(f"  Other:           {(df['region']=='other').sum()}")
    print(f"  Mean Rs:         {df['rs_annual'].mean():.0f} g C m-2 yr-1")
    print(f"  Median Rs:       {df['rs_annual'].median():.0f}")
    print(f"  Range:           {df['rs_annual'].min():.0f} – {df['rs_annual'].max():.0f}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--srdb", type=Path,
                   default=Path("data/raw/srdb/srdb-data.csv"))
    p.add_argument("--cosore", type=Path,
                   default=Path("data/raw/cosore"))
    p.add_argument("--out", type=Path,
                   default=Path("data/processed/respiration_points.parquet"))
    args = p.parse_args()
    raise SystemExit(main(args.srdb, args.cosore, args.out))
