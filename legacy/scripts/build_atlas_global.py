"""
build_atlas_global.py — extend atlas_lookup.json to non-Asia ("transfer")
cells wherever the REAL feature stack exists, without touching Asia cells.

Honest-partial scope (see BLOCKERS.md): MODIS NPP/LST is only on disk for the
Asia + US (+ Australia) study footprint (31% of global land; South America 0%).
This script therefore predicts only where bioclim + MODIS + SoilGrids all
exist; MODIS-absent cells fall out via the any-NaN rule. Nothing is fabricated.

Differences from scripts/build_atlas_lookup.py (the Asia build):
  - Grid is GLOBAL 0.5°, with the Asia bbox rectangle [25,180]x[-10,80]
    excluded so existing Asia cells are never recomputed or duplicated.
  - SoilGrids comes from REAL global rasters in data/raw/soilgrids/
    (5-15cm mean, ISRIC WCS), rescaled per src.features.SOILGRIDS_SCALE —
    NOT the Asia-training nearest-neighbour imputation (forbidden globally).
  - Every new cell is tagged "domain": "transfer".
  - Existing Asia cells are loaded verbatim from the current atlas_lookup.json
    and tagged "domain": "training" — their numeric values are untouched.

Reuses helpers/constants from scripts/build_atlas_lookup.py unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import shap
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# Reuse the Asia build's logic verbatim so transfer cells are computed the
# same way as training cells (only soil source + grid differ).
import build_atlas_lookup as A  # noqa: E402
from src.features import SOILGRIDS_SCALE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("build_atlas_global")

SOILGRIDS_PATHS = {
    v: ROOT / f"data/raw/soilgrids/{v}_5-15cm_global_0p1.tif" for v in A.SOILGRIDS_VARS
}

GLOBAL_BBOX = (-180.0, -90.0, 180.0, 90.0)
ASIA_BBOX = A.ASIA_BBOX  # (25, -10, 180, 80)
GRID = A.GRID_DEG  # 0.5


def in_asia_bbox(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    return (lon >= ASIA_BBOX[0]) & (lon <= ASIA_BBOX[2]) & \
           (lat >= ASIA_BBOX[1]) & (lat <= ASIA_BBOX[3])


def sample_soilgrids(lons, lats):
    """Sample the 8 real SoilGrids rasters, rescale to physical units, 0->NaN
    (mirrors src.features.rescale_soilgrids, which the training used)."""
    out = {}
    for var in A.SOILGRIDS_VARS:
        with rasterio.open(SOILGRIDS_PATHS[var]) as ds:
            raw = A.sample_raster(ds, lons, lats)
        raw = np.where(raw > 0, raw, np.nan)          # 0 = SoilGrids fill
        out[var] = raw * SOILGRIDS_SCALE[var]
    return out


def main(out_path: Path, checkpoint_every: int = 4000) -> None:
    # 1. Global 0.5deg grid, drop the Asia rectangle (kept verbatim later).
    lng_edges = np.arange(GLOBAL_BBOX[0], GLOBAL_BBOX[2] + GRID, GRID)
    lat_edges = np.arange(GLOBAL_BBOX[1], GLOBAL_BBOX[3] + GRID, GRID)
    lons = (lng_edges[:-1] + lng_edges[1:]) / 2
    lats = (lat_edges[:-1] + lat_edges[1:]) / 2
    cell_lon, cell_lat = np.meshgrid(lons, lats)
    cell_lon = cell_lon.ravel(); cell_lat = cell_lat.ravel()
    keep = ~in_asia_bbox(cell_lon, cell_lat)
    cell_lon, cell_lat = cell_lon[keep], cell_lat[keep]
    LOG.info("Global non-Asia grid: %d cells", len(cell_lon))

    # 2. IGBP land mask + biome class (only valid in the MODIS footprint).
    with rasterio.open(A.IGBP_PATH) as ds:
        igbp = A.sample_raster_int(ds, cell_lon, cell_lat)
    is_land = (igbp != 0) & (igbp != 17) & (igbp != 255)
    LOG.info("IGBP land cells (non-Asia): %d", int(is_land.sum()))
    cell_lon, cell_lat, igbp = cell_lon[is_land], cell_lat[is_land], igbp[is_land]

    # 3. Bioclim (global).
    feat = {}
    for var in A.BIOCLIM_VARS:
        with rasterio.open(A.WORLDCLIM_PATHS[var]) as ds:
            feat[var] = A.sample_raster(ds, cell_lon, cell_lat)

    # 4. MODIS (footprint only -> NaN elsewhere drops the cell).
    for var in A.MODIS_VARS:
        with rasterio.open(A.MODIS_PATHS[var]) as ds:
            v = A.sample_raster(ds, cell_lon, cell_lat)
        v = np.where((v < -1e6) | (v > 1e9), np.nan, v)
        feat[var] = v
    feat["lst_diurnal_range"] = feat["lst_day"] - feat["lst_night"]

    # 5. Real SoilGrids.
    soil = sample_soilgrids(cell_lon, cell_lat)
    for k, v in soil.items():
        feat[k] = v

    df = pd.DataFrame(feat)
    df["_lng"] = cell_lon; df["_lat"] = cell_lat; df["_igbp"] = igbp

    # 6. F+NPP requires bioclim + MODIS. This is the headline gate.
    n0 = len(df)
    df = df.dropna(subset=A.F_NPP_FEATURES).reset_index(drop=True)
    LOG.info("Cells with full F+NPP stack (bioclim+MODIS): %d / %d", len(df), n0)
    soil_ok = df[A.SOILGRIDS_VARS].notna().all(axis=1)
    LOG.info("  of those, with full real SoilGrids (Full+MODIS too): %d (%.1f%%)",
             int(soil_ok.sum()), 100.0 * soil_ok.mean())

    # Keep cells that support BOTH models, so the transfer cells carry the same
    # {fnpp, fullmodis} schema as Asia cells. (Cells with MODIS but no SoilGrids
    # — rare barren/ice — are dropped rather than given a fabricated soil value.)
    df = df[soil_ok].reset_index(drop=True)
    LOG.info("Final non-Asia transfer cells: %d", len(df))
    if len(df) == 0:
        LOG.error("No transfer cells — aborting.")
        return

    # 7. Engineered + land-cover one-hots (identical to the Asia build).
    df["c_n_ratio"] = df["soc"] / df["nitrogen"].replace(0, np.nan)
    df["clay_sand_ratio"] = df["clay"] / df["sand"].replace(0, np.nan)
    df["ph_optimality"] = -np.abs(df["phh2o"] - 7.0)
    df["aridity_demartonne"] = df["bio12"] / (df["bio01"] + 10.0)
    for lc in A.LANDCOVER_ONEHOT:
        df[lc] = (df["_igbp"] == int(lc.split("_")[1])).astype("float32")
    for col in A.ENGINEERED_VARS:
        df[col] = df[col].fillna(float(np.nanmedian(df[col])))

    # 8. Models + climate baseline (same training parquet as the Asia build).
    f_npp = xgb.Booster(); f_npp.load_model(str(ROOT / "data/outputs/F_NPP_model.json"))
    full_modis = xgb.Booster(); full_modis.load_model(str(ROOT / "data/outputs/Full_MODIS_model.json"))
    f_npp_metrics = json.loads((ROOT / "data/outputs/F_NPP_metrics.json").read_text())
    full_metrics = json.loads((ROOT / "data/outputs/Full_MODIS_metrics.json").read_text())
    assert f_npp_metrics["features"] == A.F_NPP_FEATURES
    assert full_metrics["features"] == A.FULL_MODIS_FEATURES
    climate_model, _ = A.train_climate_baseline(ROOT / "data/processed/training_features_v2.parquet")

    # 9. Predict.
    Xf = df[A.F_NPP_FEATURES].to_numpy("float32")
    Xfull = df[A.FULL_MODIS_FEATURES].to_numpy("float32")
    Xc = df[A.BIOCLIM_VARS].to_numpy("float32")
    pred_f = f_npp.predict(xgb.DMatrix(Xf, feature_names=A.F_NPP_FEATURES))
    pred_full = full_modis.predict(xgb.DMatrix(Xfull, feature_names=A.FULL_MODIS_FEATURES))
    pred_c = climate_model.predict(xgb.DMatrix(Xc, feature_names=A.BIOCLIM_VARS))
    anom_f = np.exp(pred_f - pred_c)
    anom_full = np.exp(pred_full - pred_c)

    # 10. Per-cell SHAP top-3 (both models), chunked + checkpointed.
    def shap_topk(model, X, names):
        expl = shap.TreeExplainer(model)
        sv = np.empty((len(X), len(names)), dtype="float32")
        for s in range(0, len(X), checkpoint_every):
            e = min(s + checkpoint_every, len(X))
            sv[s:e] = expl.shap_values(X[s:e]).astype("float32")
            LOG.info("  SHAP %d/%d", e, len(X))
        return sv
    LOG.info("SHAP F+NPP ..."); shap_f = shap_topk(f_npp, Xf, A.F_NPP_FEATURES)
    LOG.info("SHAP Full+MODIS ..."); shap_full = shap_topk(full_modis, Xfull, A.FULL_MODIS_FEATURES)
    top_f = np.argsort(-np.abs(shap_f), axis=1)[:, :3]
    top_full = np.argsort(-np.abs(shap_full), axis=1)[:, :3]
    nf = np.array(A.F_NPP_FEATURES); nfull = np.array(A.FULL_MODIS_FEATURES)

    def entries(idx_row, names, row):
        out = []
        for j in idx_row:
            key = str(names[j])
            out.append({"feature": A.FEATURE_DISPLAY.get(key, key), "key": key,
                        "value": round(float(row[j]), 4)})
        return out

    # 11. Köppen, biome, nearest-site distances (same as Asia build).
    b01 = df["bio01"].to_numpy(); b12 = df["bio12"].to_numpy()
    b14 = df["bio14"].to_numpy(); b17 = df["bio17"].to_numpy()
    kop = [A.koppen_class(t, p, x, y) for t, p, x, y in zip(b01, b12, b14, b17)]
    biome_codes = df["_igbp"].to_numpy()
    train_df = pd.read_parquet(ROOT / "data/processed/training_features_v2.parquet")
    us_df = pd.read_parquet(ROOT / "data/processed/us_validation_features_v2.parquet")
    clons, clats = df["_lng"].to_numpy(), df["_lat"].to_numpy()
    d_train = A.nearest_site_distance_km(clons, clats, train_df["longitude"].to_numpy(), train_df["latitude"].to_numpy())
    d_us = A.nearest_site_distance_km(clons, clats, us_df["longitude"].to_numpy(), us_df["latitude"].to_numpy())

    # 12. Serialise transfer cells (schema identical to Asia + "domain").
    ff = df[A.F_NPP_FEATURES].to_numpy(); fu = df[A.FULL_MODIS_FEATURES].to_numpy()
    new_cells = []
    for i in range(len(df)):
        new_cells.append({
            "lat": round(float(clats[i]), 2), "lon": round(float(clons[i]), 2),
            "fnpp": {
                "pred_log_rs": round(float(pred_f[i]), 4),
                "pred_climate_log_rs": round(float(pred_c[i]), 4),
                "anomaly": round(float(anom_f[i]), 4),
                "shap_top3": entries(top_f[i], nf, shap_f[i]),
                "features": {A.F_NPP_FEATURES[j]: round(float(ff[i, j]), 1) for j in range(len(A.F_NPP_FEATURES))},
            },
            "fullmodis": {
                "pred_log_rs": round(float(pred_full[i]), 4),
                "pred_climate_log_rs": round(float(pred_c[i]), 4),
                "anomaly": round(float(anom_full[i]), 4),
                "shap_top3": entries(top_full[i], nfull, shap_full[i]),
                "features": {A.FULL_MODIS_FEATURES[j]: round(float(fu[i, j]), 2) for j in range(len(A.FULL_MODIS_FEATURES))},
            },
            "biome_code": int(biome_codes[i]), "biome": A.IGBP_NAMES.get(int(biome_codes[i]), "Unclassified"),
            "koppen_code": kop[i][0], "koppen": kop[i][1],
            "nearest_train_km": int(round(d_train[i])), "nearest_us_km": int(round(d_us[i])),
            "domain": "transfer",
        })

    # 13. Load existing Asia atlas verbatim, tag training, merge.
    existing = json.loads((ROOT / "data/outputs/atlas_lookup.json").read_text())
    for c in existing["cells"]:
        c["domain"] = "training"
    merged = existing["cells"] + new_cells

    # 14. Per-continent anomaly sanity check on the new cells.
    LOG.info("Transfer-cell anomaly sanity (F+NPP):")
    conts = {"N.America": (-168, -52, 15, 84), "S.America": (-82, -34, -56, 13),
             "Africa": (-18, 52, -35, 38), "Europe": (-25, 25, 36, 72),
             "Oceania": (110, 180, -48, -10)}
    arr_lon = np.array([c["lon"] for c in new_cells]); arr_lat = np.array([c["lat"] for c in new_cells])
    arr_an = np.array([c["fnpp"]["anomaly"] for c in new_cells])
    for nm, (a, b, cc, d) in conts.items():
        m = (arr_lon >= a) & (arr_lon < b) & (arr_lat >= cc) & (arr_lat < d)
        if m.sum():
            LOG.info("  %-10s n=%5d  median=%.3f  p05=%.3f  p95=%.3f", nm, int(m.sum()),
                     float(np.median(arr_an[m])), float(np.percentile(arr_an[m], 5)), float(np.percentile(arr_an[m], 95)))

    # 15. Write merged atlas.
    n_train = sum(1 for c in merged if c["domain"] == "training")
    n_transfer = len(merged) - n_train
    payload = {
        "schema_version": "atlas_lookup.v4",
        "grid": {"resolution_deg": GRID, "bbox": {"min_lng": -180.0, "min_lat": -90.0, "max_lng": 180.0, "max_lat": 90.0},
                 "n_cells": len(merged)},
        "coverage": {
            "training_region": {"name": "Asia", "bbox": list(ASIA_BBOX), "n_cells": n_train},
            "transfer_region": {"name": "Rest of globe where MODIS exists", "n_cells": n_transfer},
            "note": ("Transfer cells are present only where MODIS NPP/LST exist on disk "
                     "(North America, Australia, parts of Africa/Europe). South America and "
                     "MODIS-absent regions are omitted, not predicted. See BLOCKERS.md."),
        },
        "models": existing["models"],
        "cells": merged,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    LOG.info("Wrote %s — %.2f MB, %d cells (%d training + %d transfer)",
             out_path, out_path.stat().st_size / 1e6, len(merged), n_train, n_transfer)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "data/outputs/atlas_lookup.json"))
    main_args = p.parse_args()
    main(Path(main_args.out))
