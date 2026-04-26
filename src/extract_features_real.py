"""
extract_features_real.py — sample real raster stack at training points and
across the Asia / US grids.

Produces the three feature tables consumed downstream:
  - data/processed/training_features.parquet         (Asia training points)
  - data/processed/us_validation_features.parquet    (US validation points)
  - data/processed/asia_grid_5km.parquet             (Asia prediction grid)

Run:
    python src/extract_features_real.py --config configs/mshi_geo.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features import (  # noqa: E402
    SOILGRIDS_VARS,
    add_engineered_features,
    build_grid_coords,
    default_registry,
    extract_at_points,
    rescale_soilgrids,
    sample_raster_at_points,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("mshi_geo.extract")


def _filter_to_existing(registry: Dict[str, Path]) -> Dict[str, Path]:
    """Keep only rasters that exist on disk; warn about the rest."""
    present, missing = {}, []
    for k, p in registry.items():
        if Path(p).exists():
            present[k] = p
        else:
            missing.append(k)
    if missing:
        LOG.warning("Skipping %d missing rasters (will be NaN): %s",
                    len(missing), ", ".join(sorted(missing)))
    return present


def _split_soilgrids_other(registry: Dict[str, Path]) -> tuple[Dict[str, Path], Dict[str, Path]]:
    sg = {k: v for k, v in registry.items() if k in SOILGRIDS_VARS}
    other = {k: v for k, v in registry.items() if k not in SOILGRIDS_VARS}
    return sg, other


def extract_points_region(points: pd.DataFrame, raw_dir: Path, region: str) -> pd.DataFrame:
    """
    Sample SoilGrids tiles for a region + global WorldClim/MODIS rasters.
    Returns the input DataFrame augmented with one column per feature.
    """
    if len(points) == 0:
        return points.copy()
    reg = _filter_to_existing(default_registry(raw_dir, region=region))
    sg_reg, other_reg = _split_soilgrids_other(reg)

    LOG.info("[%s] sampling %d points × %d rasters (soil=%d, other=%d)",
             region, len(points), len(reg), len(sg_reg), len(other_reg))
    out = extract_at_points(points, reg)
    return out


def build_asia_grid(raw_dir: Path, bbox: List[float], resolution_deg: float,
                    chunk_rows: int = 100) -> pd.DataFrame:
    """Build the Asia prediction grid sampled from Asia rasters."""
    reg = _filter_to_existing(default_registry(raw_dir, region="asia"))
    lons, lats = build_grid_coords(bbox, resolution_deg)
    n_cells = len(lons) * len(lats)
    LOG.info("Asia grid: %d×%d = %.2f M cells, %d rasters", len(lons), len(lats),
             n_cells / 1e6, len(reg))

    chunks: List[pd.DataFrame] = []
    for i0 in range(0, len(lats), chunk_rows):
        chunk_lats = lats[i0: i0 + chunk_rows]
        gx, gy = np.meshgrid(lons, chunk_lats)
        df = pd.DataFrame({"longitude": gx.ravel(), "latitude": gy.ravel()})
        for feat, path in reg.items():
            df[feat] = sample_raster_at_points(
                Path(path), df["longitude"].to_numpy(), df["latitude"].to_numpy()
            )
        chunks.append(df)
        LOG.info("  · sampled lat rows %d–%d (%d cells)", i0,
                 min(i0 + chunk_rows, len(lats)), len(df))
    return pd.concat(chunks, ignore_index=True)


def finalize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply SoilGrids unit conversion + engineered features."""
    out = rescale_soilgrids(df)
    out = add_engineered_features(out)
    return out


def main(cfg_path: Path) -> int:
    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]
    raw_dir = root / cfg["paths"]["raw"]
    proc_dir = root / cfg["paths"]["processed"]
    proc_dir.mkdir(parents=True, exist_ok=True)

    points_path = proc_dir / "respiration_points.parquet"
    if not points_path.exists():
        LOG.error("Missing %s — run build_target.py first.", points_path)
        return 1
    points = pd.read_parquet(points_path)
    LOG.info("Loaded %d respiration points (regions: %s)",
             len(points), dict(points["region"].value_counts()))

    asia_pts = points[points["region"] == "asia"].reset_index(drop=True)
    us_pts   = points[points["region"] == "us"].reset_index(drop=True)

    # Training table — Asia points
    asia_feat = extract_points_region(asia_pts, raw_dir, region="asia")
    asia_feat = finalize_features(asia_feat)
    train_path = root / cfg["paths"]["feature_table_train"]
    asia_feat.to_parquet(train_path, index=False)
    LOG.info("Wrote %d Asia training rows → %s", len(asia_feat), train_path)

    # US validation table
    us_feat = extract_points_region(us_pts, raw_dir, region="us")
    us_feat = finalize_features(us_feat)
    us_path = root / cfg["paths"]["feature_table_us"]
    us_feat.to_parquet(us_path, index=False)
    LOG.info("Wrote %d US validation rows → %s", len(us_feat), us_path)

    # Asia 5km grid
    asia_bbox = cfg["regions"]["asia"]["bounds"]
    asia_grid = build_asia_grid(raw_dir, asia_bbox, cfg["grid"]["iteration_deg"])
    asia_grid = finalize_features(asia_grid)
    grid_path = root / cfg["paths"]["asia_grid_5km"]
    asia_grid.to_parquet(grid_path, index=False)
    LOG.info("Wrote %d Asia grid cells → %s", len(asia_grid), grid_path)

    print("\n=== EXTRACT SUMMARY ===")
    print(f"  Train (Asia):      {len(asia_feat):>7d} rows × {asia_feat.shape[1]} cols")
    print(f"  Validate (US):     {len(us_feat):>7d} rows × {us_feat.shape[1]} cols")
    print(f"  Asia 5km grid:     {len(asia_grid):>7d} cells")
    cov_cols = [c for c in asia_feat.columns
                if c not in {"site_id", "source", "longitude", "latitude",
                             "region", "rs_annual", "log_rs_annual"}]
    if len(asia_feat) > 0:
        completeness = asia_feat[cov_cols].notna().mean().sort_values()
        print("\n  Feature completeness on training points (lowest first):")
        for c, v in completeness.head(15).items():
            print(f"    {c:<24s} {v*100:5.1f}%")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    args = p.parse_args()
    raise SystemExit(main(Path(args.config)))
