"""
build_atlas_lookup.py — generate atlas_lookup.json for the /atlas page.

Builds a 0.5° Asia grid (lng 25..180, lat -10..80), samples real features
at every land cell, predicts log Rs using the F+NPP XGBoost model and a
re-trained climate-only baseline, computes per-cell SHAP (top-3), classifies
biome via the IGBP raster, derives Köppen-Geiger zone from bio01+bio12,
and computes haversine distances to the nearest training/US-validation site.

Output: data/outputs/atlas_lookup.json with a `cells` array.

Sources actually present on this branch (claude/atlas-real-lookup):
  - data/outputs/F_NPP_model.json (XGBoost JSON, 12 features)
  - data/outputs/F_NPP_metrics.json (feature order)
  - data/outputs/F_NPP_shap.json (global SHAP ranking)
  - data/raw/modis/{npp,lst_day,lst_night,landcover_igbp}_*.tif
  - data/raw/worldclim/wc2.1_10m_bio_{1,4,5,6,12,14,15,17}.tif
    (downloaded for this script — 10' WorldClim 2.1 bioclim)
  - data/processed/training_features.parquet (615 Asia sites)
  - data/processed/us_validation_features_v2.parquet (274 US sites)

Notes / honesty:
  - The "climate baseline" needed for the anomaly ratio was re-trained
    here from training_features.parquet on the 8 bioclim features the
    F+NPP model also uses. Same XGB params as F+NPP. This mirrors the
    composite.py logic and is consistent with how the existing
    F_NPP_metrics.json baseline numbers were produced.
  - WorldClim was sampled at 10' (~18 km) rather than the 30s (~1 km)
    listed in features.py — the lookup grid is 0.5° (~55 km), so 10'
    is well below grid resolution and the dataset is small enough to
    ship with the repo if needed (~50 MB zipped, ~310 MB unzipped).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import rasterio
import shap
import xgboost as xgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("build_atlas_lookup")

ROOT = Path(__file__).resolve().parents[1]

# ─── grid + features ────────────────────────────────────────────────────────
ASIA_BBOX = (25.0, -10.0, 180.0, 80.0)  # (minLng, minLat, maxLng, maxLat)
GRID_DEG = 0.5

BIOCLIM_VARS = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
MODIS_VARS = ["npp", "lst_day", "lst_night"]
F_NPP_FEATURES = BIOCLIM_VARS + MODIS_VARS + ["lst_diurnal_range"]

WORLDCLIM_PATHS = {
    "bio01": ROOT / "data/raw/worldclim/wc2.1_10m_bio_1.tif",
    "bio04": ROOT / "data/raw/worldclim/wc2.1_10m_bio_4.tif",
    "bio05": ROOT / "data/raw/worldclim/wc2.1_10m_bio_5.tif",
    "bio06": ROOT / "data/raw/worldclim/wc2.1_10m_bio_6.tif",
    "bio12": ROOT / "data/raw/worldclim/wc2.1_10m_bio_12.tif",
    "bio14": ROOT / "data/raw/worldclim/wc2.1_10m_bio_14.tif",
    "bio15": ROOT / "data/raw/worldclim/wc2.1_10m_bio_15.tif",
    "bio17": ROOT / "data/raw/worldclim/wc2.1_10m_bio_17.tif",
}
MODIS_PATHS = {
    "npp": ROOT / "data/raw/modis/npp_2020_2024_mean.tif",
    "lst_day": ROOT / "data/raw/modis/lst_day_2020_2024_mean.tif",
    "lst_night": ROOT / "data/raw/modis/lst_night_2020_2024_mean.tif",
}
IGBP_PATH = ROOT / "data/raw/modis/landcover_igbp_2023.tif"


# ─── IGBP class names (1-17, MCD12Q1 LC_Type1) ──────────────────────────────
IGBP_NAMES = {
    0: "Water",
    1: "Evergreen needleleaf forests",
    2: "Evergreen broadleaf forests",
    3: "Deciduous needleleaf forests",
    4: "Deciduous broadleaf forests",
    5: "Mixed forests",
    6: "Closed shrublands",
    7: "Open shrublands",
    8: "Woody savannas",
    9: "Savannas",
    10: "Grasslands",
    11: "Permanent wetlands",
    12: "Croplands",
    13: "Urban and built-up",
    14: "Cropland/natural vegetation mosaic",
    15: "Permanent snow and ice",
    16: "Barren",
    17: "Water bodies",
    255: "Unclassified",
}


# ─── Köppen-Geiger classification ───────────────────────────────────────────
# Uses bio01 (MAT °C), bio12 (annual precip mm), bio14 (precip of driest
# month, mm), and bio17 (precip of driest quarter, mm) to recover the
# standard Trewartha/Köppen-Geiger main classes the MSHI paper uses.
def koppen_class(mat_c: float, map_mm: float, bio14_mm: float,
                 bio17_mm: float) -> Tuple[str, str]:
    """Return (code, label) for the Köppen-Geiger main class."""
    if mat_c is None or np.isnan(mat_c):
        return ("?", "Unknown")

    # B (dry climates) — based on aridity threshold (Trewartha simplified)
    threshold = 10 * mat_c + (140 if mat_c > 0 else 0)
    if map_mm < threshold * 0.5:
        return ("BWh", "Hot desert") if mat_c >= 18 else ("BWk", "Cold desert")
    if map_mm < threshold:
        return ("BSh", "Hot steppe") if mat_c >= 18 else ("BSk", "Cold steppe")

    # A (tropical) — mean annual temp >= 18 °C
    if mat_c >= 18:
        if bio14_mm >= 60:
            return ("Af", "Tropical rainforest")
        # Am vs Aw: Am has heavy total precip with a short dry season
        am_threshold = 100 - map_mm / 25.0
        if bio14_mm >= am_threshold:
            return ("Am", "Tropical monsoon")
        return ("Aw", "Tropical savanna (dry winter)")

    # C (temperate) — coldest month between -3 and 18 °C  (using mat as proxy)
    if mat_c >= 10:
        if bio17_mm < 30:
            return ("Cwa", "Humid subtropical, dry winter")
        return ("Cfa", "Humid subtropical")

    # D (continental) — clear cold winters
    if mat_c >= 3:
        if bio17_mm < 50:
            return ("Dwa", "Humid continental, dry winter")
        return ("Dfa", "Humid continental")
    if mat_c >= -3:
        return ("Dfb", "Cold continental")
    if mat_c >= -38:
        return ("Dfc", "Subarctic boreal")
    # E (polar)
    return ("ET", "Tundra")


# ─── Feature-display name mapping for SHAP top-3 ────────────────────────────
FEATURE_DISPLAY = {
    "bio01": "Mean annual temperature",
    "bio04": "Temperature seasonality",
    "bio05": "Max temp of warmest month",
    "bio06": "Min temp of coldest month",
    "bio12": "Annual precipitation",
    "bio14": "Precip of driest month",
    "bio15": "Precip seasonality",
    "bio17": "Precip of driest quarter",
    "npp": "MODIS NPP",
    "lst_day": "MODIS LST (day)",
    "lst_night": "MODIS LST (night)",
    "lst_diurnal_range": "LST diurnal range",
}


# ─── Sampling helpers ───────────────────────────────────────────────────────
def sample_raster(ds: rasterio.DatasetReader, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Sample a raster at (lon, lat) points. Returns float64 array; NaN where outside / nodata."""
    coords = list(zip(lons, lats))
    out = np.full(len(coords), np.nan, dtype="float64")
    for i, val in enumerate(ds.sample(coords)):
        if val is None or len(val) == 0:
            continue
        v = float(val[0])
        if ds.nodata is not None and v == ds.nodata:
            continue
        out[i] = v
    return out


def sample_raster_int(ds: rasterio.DatasetReader, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Sample uint8 raster (e.g. IGBP land cover). Returns int array; 255 where outside."""
    coords = list(zip(lons, lats))
    out = np.full(len(coords), 255, dtype="int16")
    for i, val in enumerate(ds.sample(coords)):
        if val is None or len(val) == 0:
            continue
        out[i] = int(val[0])
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def nearest_site_distance_km(cell_lons, cell_lats, site_lons, site_lats):
    """Vectorised: for each cell, nearest of the site points (in km).
    Computes in chunks of cells to keep memory reasonable on ~50K x ~615."""
    n = len(cell_lons)
    out = np.full(n, np.inf, dtype="float64")
    chunk = 4000
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        cl_lat = cell_lats[start:end][:, None]
        cl_lon = cell_lons[start:end][:, None]
        s_lat = site_lats[None, :]
        s_lon = site_lons[None, :]
        d = haversine_km(cl_lat, cl_lon, s_lat, s_lon)
        out[start:end] = d.min(axis=1)
    return out


# ─── Climate baseline trainer ───────────────────────────────────────────────
def train_climate_baseline(train_path: Path) -> Tuple[xgb.Booster, List[str]]:
    df = pd.read_parquet(train_path)
    feats = BIOCLIM_VARS
    df = df.dropna(subset=feats + ["log_rs_annual"])
    LOG.info("Training climate baseline on %d rows × %d features", len(df), len(feats))
    dtrain = xgb.DMatrix(df[feats].to_numpy("float32"), label=df["log_rs_annual"].to_numpy("float32"), feature_names=feats)
    params = dict(
        objective="reg:squarederror",
        eta=0.05,
        max_depth=3,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=4,
        reg_alpha=0.5,
        reg_lambda=2.0,
        verbosity=0,
    )
    booster = xgb.train(params, dtrain, num_boost_round=250)
    return booster, feats


# ─── Main ───────────────────────────────────────────────────────────────────
def main(out_path: Path) -> None:
    # 1. Build the 0.5° grid
    lng_edges = np.arange(ASIA_BBOX[0], ASIA_BBOX[2] + GRID_DEG, GRID_DEG)
    lat_edges = np.arange(ASIA_BBOX[1], ASIA_BBOX[3] + GRID_DEG, GRID_DEG)
    lons = (lng_edges[:-1] + lng_edges[1:]) / 2
    lats = (lat_edges[:-1] + lat_edges[1:]) / 2
    cell_lon, cell_lat = np.meshgrid(lons, lats)
    cell_lon = cell_lon.ravel()
    cell_lat = cell_lat.ravel()
    LOG.info("Grid: %d cells (%d lng × %d lat)", len(cell_lon), len(lons), len(lats))

    # 2. Sample IGBP land cover (used as land mask + biome class)
    LOG.info("Sampling IGBP land cover ...")
    with rasterio.open(IGBP_PATH) as ds:
        igbp = sample_raster_int(ds, cell_lon, cell_lat)

    # IGBP class 0 (water) and 17 (water bodies) are not-land. Drop them, but
    # keep all other classes including 15 (snow/ice), 16 (barren) — they're
    # legitimate land in Asia (Tibetan Plateau etc.).
    is_land = (igbp != 0) & (igbp != 17) & (igbp != 255)
    LOG.info("Land cells: %d / %d (%.1f%%)", is_land.sum(), len(cell_lon),
             100.0 * is_land.sum() / len(cell_lon))

    cell_lon = cell_lon[is_land]
    cell_lat = cell_lat[is_land]
    igbp = igbp[is_land]

    # 3. Sample bioclim features
    LOG.info("Sampling 8 WorldClim bioclim rasters ...")
    feat_arrays: Dict[str, np.ndarray] = {}
    for var in BIOCLIM_VARS:
        with rasterio.open(WORLDCLIM_PATHS[var]) as ds:
            feat_arrays[var] = sample_raster(ds, cell_lon, cell_lat)

    # 4. Sample MODIS features
    LOG.info("Sampling 3 MODIS rasters ...")
    for var in MODIS_VARS:
        with rasterio.open(MODIS_PATHS[var]) as ds:
            v = sample_raster(ds, cell_lon, cell_lat)
        # MODIS rasters in this dataset don't define nodata; treat extreme
        # placeholder values as missing.
        v = np.where((v < -1e6) | (v > 1e9), np.nan, v)
        feat_arrays[var] = v

    # 5. Derived feature: LST diurnal range
    feat_arrays["lst_diurnal_range"] = feat_arrays["lst_day"] - feat_arrays["lst_night"]

    # 6. Drop cells with any-NaN in features. Most likely these are:
    #    - Outside MODIS coverage (e.g. western Asia / Mediterranean)
    #    - Outside WorldClim coverage (almost never)
    feat_df = pd.DataFrame(feat_arrays, index=range(len(cell_lon)))
    feat_df["_lng"] = cell_lon
    feat_df["_lat"] = cell_lat
    feat_df["_igbp"] = igbp
    before = len(feat_df)
    feat_df = feat_df.dropna(subset=F_NPP_FEATURES)
    LOG.info("Cells with all features non-NaN: %d / %d", len(feat_df), before)

    # 7. Load F+NPP model (XGBoost). The saved JSON has empty feature_names,
    #    so we rebuild the DMatrix with the documented feature order from
    #    F_NPP_metrics.json.
    LOG.info("Loading F+NPP model ...")
    f_npp = xgb.Booster()
    f_npp.load_model(str(ROOT / "data/outputs/F_NPP_model.json"))
    f_npp_metrics = json.loads((ROOT / "data/outputs/F_NPP_metrics.json").read_text())
    f_npp_features = f_npp_metrics["features"]
    assert f_npp_features == F_NPP_FEATURES, (f_npp_features, F_NPP_FEATURES)

    # 8. Train climate baseline (same params, only bioclim features)
    LOG.info("Training climate baseline ...")
    climate_model, climate_features = train_climate_baseline(
        ROOT / "data/processed/training_features.parquet"
    )

    # 9. Predict with both models
    LOG.info("Predicting with F+NPP and climate baseline ...")
    Xf = feat_df[F_NPP_FEATURES].to_numpy("float32")
    Xc = feat_df[BIOCLIM_VARS].to_numpy("float32")

    pred_f_npp = f_npp.predict(xgb.DMatrix(Xf, feature_names=F_NPP_FEATURES))
    pred_clim = climate_model.predict(xgb.DMatrix(Xc, feature_names=BIOCLIM_VARS))

    # anomaly ratio = exp(F+NPP) / exp(climate) = exp(F+NPP - climate)
    anomaly = np.exp(pred_f_npp - pred_clim)

    # 10. SHAP per-cell via TreeExplainer for the F+NPP model
    LOG.info("Computing per-cell SHAP for F+NPP ...")
    explainer = shap.TreeExplainer(f_npp)
    # batch SHAP to keep memory bounded
    shap_vals = np.empty((len(Xf), len(F_NPP_FEATURES)), dtype="float32")
    chunk = 5000
    for start in range(0, len(Xf), chunk):
        end = min(start + chunk, len(Xf))
        sv = explainer.shap_values(Xf[start:end])
        shap_vals[start:end] = sv.astype("float32")
        LOG.info("  SHAP %d / %d", end, len(Xf))

    # 11. Köppen classification
    LOG.info("Köppen classification ...")
    bio01 = feat_df["bio01"].to_numpy()
    bio12 = feat_df["bio12"].to_numpy()
    bio14 = feat_df["bio14"].to_numpy()
    bio17 = feat_df["bio17"].to_numpy()
    koppen_codes = []
    koppen_labels = []
    for t, p, b14, b17 in zip(bio01, bio12, bio14, bio17):
        c, l = koppen_class(t, p, b14, b17)
        koppen_codes.append(c)
        koppen_labels.append(l)

    # 12. Biome lookup
    biome_codes = feat_df["_igbp"].to_numpy()
    biome_labels = [IGBP_NAMES.get(int(c), "Unclassified") for c in biome_codes]

    # 13. Distances to training and US validation sites
    LOG.info("Computing nearest-site distances ...")
    train_df = pd.read_parquet(ROOT / "data/processed/training_features.parquet")
    us_df = pd.read_parquet(ROOT / "data/processed/us_validation_features_v2.parquet")

    train_lons = train_df["longitude"].to_numpy()
    train_lats = train_df["latitude"].to_numpy()
    us_lons = us_df["longitude"].to_numpy()
    us_lats = us_df["latitude"].to_numpy()

    cell_lons = feat_df["_lng"].to_numpy()
    cell_lats = feat_df["_lat"].to_numpy()

    d_train = nearest_site_distance_km(cell_lons, cell_lats, train_lons, train_lats)
    d_us = nearest_site_distance_km(cell_lons, cell_lats, us_lons, us_lats)

    # 14. Build SHAP top-3 per cell
    LOG.info("Picking top-3 SHAP features per cell ...")
    abs_shap = np.abs(shap_vals)
    # argsort descending then take top 3
    top3_idx = np.argsort(-abs_shap, axis=1)[:, :3]
    feature_names_arr = np.array(F_NPP_FEATURES)

    # 15. Serialize
    LOG.info("Serialising ...")
    cells = []
    for i in range(len(feat_df)):
        lon = float(cell_lons[i])
        lat = float(cell_lats[i])
        idxs = top3_idx[i]
        shap_top3 = [
            {
                "feature": FEATURE_DISPLAY[feature_names_arr[j]],
                "value": round(float(shap_vals[i, j]), 4),
            }
            for j in idxs
        ]
        cells.append(
            {
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "pred_log_rs": round(float(pred_f_npp[i]), 4),
                "pred_climate_log_rs": round(float(pred_clim[i]), 4),
                "anomaly": round(float(anomaly[i]), 4),
                "shap_top3": shap_top3,
                "biome_code": int(biome_codes[i]),
                "biome": biome_labels[i],
                "koppen_code": koppen_codes[i],
                "koppen": koppen_labels[i],
                "nearest_train_km": int(round(d_train[i])),
                "nearest_us_km": int(round(d_us[i])),
            }
        )

    # 16. Anomaly distribution check
    anomaly_arr = np.array([c["anomaly"] for c in cells])
    LOG.info(
        "Anomaly: n=%d, median=%.3f, p05=%.3f, p95=%.3f, min=%.3f, max=%.3f",
        len(anomaly_arr),
        float(np.median(anomaly_arr)),
        float(np.percentile(anomaly_arr, 5)),
        float(np.percentile(anomaly_arr, 95)),
        float(anomaly_arr.min()),
        float(anomaly_arr.max()),
    )

    # 17. Write JSON
    payload = {
        "schema_version": "atlas_lookup.v1",
        "grid": {
            "resolution_deg": GRID_DEG,
            "bbox": {"min_lng": ASIA_BBOX[0], "min_lat": ASIA_BBOX[1],
                     "max_lng": ASIA_BBOX[2], "max_lat": ASIA_BBOX[3]},
            "n_cells": len(cells),
        },
        "model": {
            "name": "F+NPP",
            "n_features": len(F_NPP_FEATURES),
            "features": F_NPP_FEATURES,
            "training_n_asia": int(f_npp_metrics["n_train"]),
            "validation_n_us": int(f_npp_metrics["n_us"]),
            "transfer_r2": round(float(f_npp_metrics["transfer"]["r2"]), 3),
            "transfer_ci_low": round(float(f_npp_metrics["transfer"]["ci_low"]), 3),
            "transfer_ci_high": round(float(f_npp_metrics["transfer"]["ci_high"]), 3),
        },
        "cells": cells,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    size = out_path.stat().st_size
    LOG.info("Wrote %s — %.2f MB, %d cells", out_path, size / 1e6, len(cells))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "data/outputs/atlas_lookup.json"))
    args = p.parse_args()
    main(Path(args.out))
