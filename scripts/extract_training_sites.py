"""
extract_training_sites.py — emit /public/data/training_sites.json for the
atlas's "toggle density" overlay.

Reads the merged training-set parquet (3,000-row, post-merge) and outputs
the subset of points that fall inside the Asia bbox (the F+NPP model's
training cohort), with their longitude/latitude/source per the SRDB +
COSORE provenance column.

Output: data/outputs/training_sites.json
  { "n_sites": 615, "sites": [{"lon": ..., "lat": ..., "source": "srdb"}, ...] }
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("extract_training_sites")

ROOT = Path(__file__).resolve().parents[1]

# Asia bbox used by the F+NPP training set + the /atlas page.
ASIA_BBOX = {"min_lng": 25.0, "max_lng": 180.0, "min_lat": -10.0, "max_lat": 80.0}


def main(out_path: Path) -> None:
    parquet = ROOT / "data/processed/training_features_v2.parquet"
    df = pd.read_parquet(parquet)
    LOG.info("Loaded %d rows from %s", len(df), parquet.name)

    needed = {"longitude", "latitude"}
    missing = needed - set(df.columns)
    if missing:
        raise RuntimeError(f"training_features.parquet missing required columns: {missing}")

    # Filter to Asia bbox (the training cohort is already Asia-only, but
    # this is defensive against parquet variants that include US rows).
    in_asia = (
        (df["longitude"] >= ASIA_BBOX["min_lng"])
        & (df["longitude"] <= ASIA_BBOX["max_lng"])
        & (df["latitude"] >= ASIA_BBOX["min_lat"])
        & (df["latitude"] <= ASIA_BBOX["max_lat"])
    )
    asia = df.loc[in_asia].copy()
    LOG.info("Asia-bbox training rows: %d / %d", len(asia), len(df))

    # `source` column exists in pre-merge parquets but not always in the
    # post-merge superset; default to 'srdb' (the dominant source).
    if "source" in asia.columns:
        sources = asia["source"].astype(str).fillna("srdb").str.lower()
    else:
        sources = pd.Series(["srdb"] * len(asia), index=asia.index)

    sites = [
        {
            "lon": round(float(lng), 4),
            "lat": round(float(lat), 4),
            "source": src,
        }
        for lng, lat, src in zip(asia["longitude"], asia["latitude"], sources)
    ]

    payload = {
        "schema_version": "training_sites.v1",
        "n_sites": len(sites),
        "bbox": ASIA_BBOX,
        "sites": sites,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    LOG.info("Wrote %s — %d sites, %.1f kB", out_path, len(sites),
             out_path.stat().st_size / 1024)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "data/outputs/training_sites.json"))
    args = p.parse_args()
    main(Path(args.out))
