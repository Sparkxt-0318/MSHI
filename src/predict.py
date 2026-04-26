"""
predict.py — run MSHI-Geo inference across an entire Asia grid.

Streams the prediction grid through the model in chunks to keep memory low.
Writes a GeoTIFF where each pixel is predicted log_mbc (and a back-transformed
mbc_pred column inside the parquet output).

Run:
    python src/predict.py --config configs/mshi_geo.yaml --resolution 5km
    python src/predict.py --config configs/mshi_geo.yaml --resolution 1km
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yaml

LOG = logging.getLogger("mshi_geo.predict")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def predict_grid(
    grid_df: pd.DataFrame,
    model,
    feature_cols: List[str],
    chunk: int = 200_000,
) -> np.ndarray:
    """Stream predictions through the model in chunks."""
    out = np.full(len(grid_df), np.nan, dtype="float32")
    valid = grid_df[feature_cols].notna().all(axis=1).to_numpy()
    idx = np.where(valid)[0]
    for start in range(0, len(idx), chunk):
        sl = idx[start : start + chunk]
        out[sl] = model.predict(grid_df.iloc[sl][feature_cols].to_numpy("float32"))
    return out


def write_geotiff(
    lons: np.ndarray, lats: np.ndarray, values: np.ndarray, out_path: Path,
    nodata: float = -9999.0,
) -> None:
    import rasterio
    from rasterio.transform import from_origin

    nx = len(np.unique(lons))
    ny = len(np.unique(lats))
    grid = values.reshape(ny, nx)
    grid = np.flipud(grid)  # raster origin is top-left

    res_x = (lons.max() - lons.min()) / (nx - 1)
    res_y = (lats.max() - lats.min()) / (ny - 1)
    transform = from_origin(
        west=lons.min() - res_x / 2,
        north=lats.max() + res_y / 2,
        xsize=res_x,
        ysize=res_y,
    )
    grid = np.where(np.isnan(grid), nodata, grid)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w", driver="GTiff",
        height=ny, width=nx, count=1, dtype="float32",
        crs="EPSG:4326", transform=transform, nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(grid.astype("float32"), 1)


def main(cfg_path: Path, resolution_label: str) -> int:
    import xgboost as xgb

    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]

    if resolution_label == "5km":
        res = cfg["grid"]["iteration_deg"]
        grid_path = root / cfg["paths"]["asia_grid_5km"]
        out_tif   = root / cfg["paths"]["prediction_5km"]
    elif resolution_label == "1km":
        res = cfg["grid"]["final_deg"]
        grid_path = root / cfg["paths"]["asia_grid_1km"]
        out_tif   = root / cfg["paths"]["prediction_1km"]
    else:
        raise ValueError("--resolution must be 5km or 1km")

    if not grid_path.exists():
        LOG.error("Grid not found: %s", grid_path)
        LOG.error("Build it first via build_grid step in run.sh")
        return 1

    grid_df = pd.read_parquet(grid_path)
    LOG.info("Loaded grid: %d rows", len(grid_df))

    model = xgb.XGBRegressor()
    model.load_model(str(root / cfg["paths"]["model"]))

    metrics_meta = json.loads(
        (root / "data" / "outputs" / "training_metrics.json").read_text()
    )
    feature_cols = metrics_meta["feature_cols"]

    log_mbc = predict_grid(grid_df, model, feature_cols)
    mbc_pred = np.exp(log_mbc)

    grid_df["log_mbc_pred"] = log_mbc
    grid_df["mbc_pred"]     = mbc_pred

    out_parquet = grid_path.with_name(grid_path.stem + "_predictions.parquet")
    grid_df[["longitude", "latitude", "log_mbc_pred", "mbc_pred"]].to_parquet(
        out_parquet, index=False
    )
    LOG.info("Saved predictions parquet → %s", out_parquet)

    write_geotiff(
        grid_df["longitude"].to_numpy(),
        grid_df["latitude"].to_numpy(),
        log_mbc,
        out_tif,
    )
    LOG.info("Saved GeoTIFF → %s", out_tif)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    p.add_argument("--resolution", default="5km", choices=["5km", "1km"])
    args = p.parse_args()
    raise SystemExit(main(Path(args.config), args.resolution))
