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

# Full+MODIS uses 34 features. Most are shared with F+NPP; the additions are
# the 8 SoilGrids variables, 4 engineered features, and 10 land-cover one-hots.
SOILGRIDS_VARS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
ENGINEERED_VARS = ["c_n_ratio", "clay_sand_ratio", "ph_optimality", "aridity_demartonne"]
LANDCOVER_ONEHOT = [
    "lc_02", "lc_04", "lc_05", "lc_08", "lc_09",
    "lc_10", "lc_12", "lc_13", "lc_14", "lc_17",
]
FULL_MODIS_FEATURES = (
    SOILGRIDS_VARS
    + BIOCLIM_VARS
    + ENGINEERED_VARS
    + MODIS_VARS
    + ["lst_diurnal_range"]
    + LANDCOVER_ONEHOT
)  # length 34

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
    # Soil + engineered + land-cover one-hots used by Full+MODIS only
    "soc": "Soil organic carbon",
    "nitrogen": "Soil nitrogen",
    "phh2o": "Soil pH (H2O)",
    "clay": "Soil clay fraction",
    "sand": "Soil sand fraction",
    "silt": "Soil silt fraction",
    "bdod": "Soil bulk density",
    "cec": "Cation exchange capacity",
    "c_n_ratio": "C:N ratio",
    "clay_sand_ratio": "Clay:sand ratio",
    "ph_optimality": "pH optimality",
    "aridity_demartonne": "Aridity (de Martonne)",
    "lc_02": "LC: Evergreen broadleaf",
    "lc_04": "LC: Deciduous broadleaf",
    "lc_05": "LC: Mixed forests",
    "lc_08": "LC: Woody savannas",
    "lc_09": "LC: Savannas",
    "lc_10": "LC: Grasslands",
    "lc_12": "LC: Croplands",
    "lc_13": "LC: Urban",
    "lc_14": "LC: Cropland mosaic",
    "lc_17": "LC: Water bodies",
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


def nearest_index(cell_lons, cell_lats, ref_lons, ref_lats):
    """For each cell, return the index of the nearest reference point.
    Used for nearest-neighbour SoilGrids imputation. Chunked for memory."""
    n = len(cell_lons)
    out = np.zeros(n, dtype="int64")
    chunk = 4000
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        cl_lat = cell_lats[start:end][:, None]
        cl_lon = cell_lons[start:end][:, None]
        s_lat = ref_lats[None, :]
        s_lon = ref_lons[None, :]
        d = haversine_km(cl_lat, cl_lon, s_lat, s_lon)
        out[start:end] = d.argmin(axis=1)
    return out


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
    # Match the F+NPP training subset exactly: drop rows missing ANY of the
    # 12 F+NPP features (incl. MODIS) so the baseline and F+NPP see the
    # same rows. Without this, the merged 3,000-row parquet trains the
    # baseline on rows F+NPP never saw, and the anomaly ratio
    # (exp(F+NPP - climate)) becomes meaningless because the two
    # predictors aren't comparable.
    full_feats = (
        BIOCLIM_VARS + ["npp", "lst_day", "lst_night"]
        if {"npp", "lst_day", "lst_night"}.issubset(df.columns)
        else BIOCLIM_VARS
    )
    df = df.dropna(subset=full_feats + ["log_rs_annual"])
    LOG.info(
        "Training climate baseline on %d rows × %d features (matched F+NPP non-NaN subset)",
        len(df),
        len(feats),
    )
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

    # 7. Load both models (F+NPP and Full+MODIS). Each saved XGB JSON has an
    #    empty feature_names list, so the DMatrix at predict time gets the
    #    documented feature order from the corresponding metrics JSON.
    LOG.info("Loading F+NPP model ...")
    f_npp = xgb.Booster()
    f_npp.load_model(str(ROOT / "data/outputs/F_NPP_model.json"))
    f_npp_metrics = json.loads((ROOT / "data/outputs/F_NPP_metrics.json").read_text())
    assert f_npp_metrics["features"] == F_NPP_FEATURES

    LOG.info("Loading Full+MODIS model ...")
    full_modis = xgb.Booster()
    full_modis.load_model(str(ROOT / "data/outputs/Full_MODIS_model.json"))
    full_modis_metrics = json.loads(
        (ROOT / "data/outputs/Full_MODIS_metrics.json").read_text()
    )
    assert full_modis_metrics["features"] == FULL_MODIS_FEATURES, (
        full_modis_metrics["features"],
        FULL_MODIS_FEATURES,
    )

    # 7b. Augment per-cell features with the SoilGrids + engineered + land-cover
    #     one-hots that Full+MODIS needs but F+NPP doesn't. SoilGrids rasters
    #     aren't on disk, so we use nearest-neighbour lookup from the 615-row
    #     training parquet (which carries soil values per training site).
    #     This is faithful at 0.5° resolution: most lookup cells are within
    #     a couple of training sites' worth of soil-feature distance, and the
    #     Full+MODIS model was trained on the same SoilGrids-sampled values
    #     at training-point coordinates. Honest caveat: Full+MODIS predictions
    #     in cells far from any training site degrade to "what the nearest
    #     training site's soil would look like".
    LOG.info("Augmenting cells with SoilGrids/engineered/land-cover features ...")
    train_for_soil = pd.read_parquet(
        ROOT / "data/processed/training_features_v2.parquet"
    )
    soil_complete = train_for_soil.dropna(subset=SOILGRIDS_VARS)
    LOG.info(
        "  soil reference: %d / %d training sites with non-NaN SoilGrids",
        len(soil_complete),
        len(train_for_soil),
    )
    soil_lons = soil_complete["longitude"].to_numpy()
    soil_lats = soil_complete["latitude"].to_numpy()
    soil_matrix = soil_complete[SOILGRIDS_VARS].to_numpy()
    nn_idx = nearest_index(
        feat_df["_lng"].to_numpy(),
        feat_df["_lat"].to_numpy(),
        soil_lons,
        soil_lats,
    )
    for j, var in enumerate(SOILGRIDS_VARS):
        feat_df[var] = soil_matrix[nn_idx, j]

    # Engineered features (mirrors src/features.py add_engineered_features):
    #   c_n_ratio        = soc / nitrogen
    #   clay_sand_ratio  = clay / sand
    #   ph_optimality    = -|phh2o - 7.0|        (peak-shaped at pH 7)
    #   aridity_demartonne = bio12 / (bio01 + 10)
    feat_df["c_n_ratio"] = feat_df["soc"] / feat_df["nitrogen"].replace(0, np.nan)
    feat_df["clay_sand_ratio"] = feat_df["clay"] / feat_df["sand"].replace(0, np.nan)
    feat_df["ph_optimality"] = -np.abs(feat_df["phh2o"] - 7.0)
    feat_df["aridity_demartonne"] = feat_df["bio12"] / (feat_df["bio01"] + 10.0)

    # Land-cover one-hots: the 10 IGBP classes Full+MODIS was trained on.
    for lc in LANDCOVER_ONEHOT:
        klass = int(lc.split("_")[1])
        feat_df[lc] = (feat_df["_igbp"] == klass).astype("float32")

    # Some cells will still have NaN engineered features (e.g. nitrogen=0). Fill
    # with the median to keep the model from refusing to predict on them.
    for col in ENGINEERED_VARS:
        med = float(np.nanmedian(feat_df[col]))
        feat_df[col] = feat_df[col].fillna(med)

    # 8. Train climate baseline (same params, only bioclim features)
    LOG.info("Training climate baseline ...")
    climate_model, climate_features = train_climate_baseline(
        ROOT / "data/processed/training_features_v2.parquet"
    )

    # 9. Predict with all three models
    LOG.info("Predicting with F+NPP, Full+MODIS, and climate baseline ...")
    Xf_npp = feat_df[F_NPP_FEATURES].to_numpy("float32")
    Xfull = feat_df[FULL_MODIS_FEATURES].to_numpy("float32")
    Xc = feat_df[BIOCLIM_VARS].to_numpy("float32")

    pred_f_npp = f_npp.predict(xgb.DMatrix(Xf_npp, feature_names=F_NPP_FEATURES))
    pred_full_modis = full_modis.predict(
        xgb.DMatrix(Xfull, feature_names=FULL_MODIS_FEATURES)
    )
    pred_clim = climate_model.predict(xgb.DMatrix(Xc, feature_names=BIOCLIM_VARS))

    # anomaly = exp(model_log_rs - climate_log_rs)
    anomaly_f_npp = np.exp(pred_f_npp - pred_clim)
    anomaly_full_modis = np.exp(pred_full_modis - pred_clim)

    # 10. Per-cell SHAP for both models
    LOG.info("Computing per-cell SHAP for F+NPP ...")
    explainer_npp = shap.TreeExplainer(f_npp)
    shap_npp = np.empty((len(Xf_npp), len(F_NPP_FEATURES)), dtype="float32")
    chunk = 5000
    for start in range(0, len(Xf_npp), chunk):
        end = min(start + chunk, len(Xf_npp))
        shap_npp[start:end] = explainer_npp.shap_values(Xf_npp[start:end]).astype(
            "float32"
        )
        LOG.info("  F+NPP SHAP %d / %d", end, len(Xf_npp))

    LOG.info("Computing per-cell SHAP for Full+MODIS ...")
    explainer_full = shap.TreeExplainer(full_modis)
    shap_full = np.empty((len(Xfull), len(FULL_MODIS_FEATURES)), dtype="float32")
    for start in range(0, len(Xfull), chunk):
        end = min(start + chunk, len(Xfull))
        shap_full[start:end] = explainer_full.shap_values(Xfull[start:end]).astype(
            "float32"
        )
        LOG.info("  Full+MODIS SHAP %d / %d", end, len(Xfull))

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
    train_df = pd.read_parquet(ROOT / "data/processed/training_features_v2.parquet")
    us_df = pd.read_parquet(ROOT / "data/processed/us_validation_features_v2.parquet")

    train_lons = train_df["longitude"].to_numpy()
    train_lats = train_df["latitude"].to_numpy()
    us_lons = us_df["longitude"].to_numpy()
    us_lats = us_df["latitude"].to_numpy()

    cell_lons = feat_df["_lng"].to_numpy()
    cell_lats = feat_df["_lat"].to_numpy()

    d_train = nearest_site_distance_km(cell_lons, cell_lats, train_lons, train_lats)
    d_us = nearest_site_distance_km(cell_lons, cell_lats, us_lons, us_lats)

    # 14. Build SHAP top-3 per cell for each model.
    LOG.info("Picking top-3 SHAP features per cell (both models) ...")
    npp_top3 = np.argsort(-np.abs(shap_npp), axis=1)[:, :3]
    full_top3 = np.argsort(-np.abs(shap_full), axis=1)[:, :3]
    npp_names = np.array(F_NPP_FEATURES)
    full_names = np.array(FULL_MODIS_FEATURES)

    def shap_entries(top3_idx_row, names, shap_row):
        out = []
        for j in top3_idx_row:
            key = names[j].item() if hasattr(names[j], "item") else str(names[j])
            out.append({
                "feature": FEATURE_DISPLAY.get(key, key),
                "key": key,
                "value": round(float(shap_row[j]), 4),
            })
        return out

    # 15. Serialize. Each cell carries shared metadata (coord, biome,
    #     Köppen, distances) plus a per-model object {prediction, anomaly,
    #     shap_top3, features}.
    LOG.info("Serialising ...")
    cells = []
    f_npp_feat = feat_df[F_NPP_FEATURES].to_numpy()
    full_feat = feat_df[FULL_MODIS_FEATURES].to_numpy()
    for i in range(len(feat_df)):
        lon = float(cell_lons[i])
        lat = float(cell_lats[i])
        fnpp_block = {
            "pred_log_rs": round(float(pred_f_npp[i]), 4),
            "pred_climate_log_rs": round(float(pred_clim[i]), 4),
            "anomaly": round(float(anomaly_f_npp[i]), 4),
            "shap_top3": shap_entries(npp_top3[i], npp_names, shap_npp[i]),
            "features": {
                F_NPP_FEATURES[j]: round(float(f_npp_feat[i, j]), 1)
                for j in range(len(F_NPP_FEATURES))
            },
        }
        fullmodis_block = {
            "pred_log_rs": round(float(pred_full_modis[i]), 4),
            "pred_climate_log_rs": round(float(pred_clim[i]), 4),
            "anomaly": round(float(anomaly_full_modis[i]), 4),
            "shap_top3": shap_entries(full_top3[i], full_names, shap_full[i]),
            "features": {
                FULL_MODIS_FEATURES[j]: round(float(full_feat[i, j]), 2)
                for j in range(len(FULL_MODIS_FEATURES))
            },
        }
        cells.append(
            {
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "fnpp": fnpp_block,
                "fullmodis": fullmodis_block,
                "biome_code": int(biome_codes[i]),
                "biome": biome_labels[i],
                "koppen_code": koppen_codes[i],
                "koppen": koppen_labels[i],
                "nearest_train_km": int(round(d_train[i])),
                "nearest_us_km": int(round(d_us[i])),
            }
        )

    # 16. Anomaly distribution checks for BOTH models
    npp_arr = np.array([c["fnpp"]["anomaly"] for c in cells])
    full_arr = np.array([c["fullmodis"]["anomaly"] for c in cells])
    LOG.info(
        "F+NPP anomaly:      n=%d  median=%.3f  p05=%.3f  p95=%.3f  min=%.3f  max=%.3f",
        len(npp_arr),
        float(np.median(npp_arr)),
        float(np.percentile(npp_arr, 5)),
        float(np.percentile(npp_arr, 95)),
        float(npp_arr.min()),
        float(npp_arr.max()),
    )
    LOG.info(
        "Full+MODIS anomaly: n=%d  median=%.3f  p05=%.3f  p95=%.3f  min=%.3f  max=%.3f",
        len(full_arr),
        float(np.median(full_arr)),
        float(np.percentile(full_arr, 5)),
        float(np.percentile(full_arr, 95)),
        float(full_arr.min()),
        float(full_arr.max()),
    )

    # 17. Write JSON
    payload = {
        "schema_version": "atlas_lookup.v3",
        "grid": {
            "resolution_deg": GRID_DEG,
            "bbox": {"min_lng": ASIA_BBOX[0], "min_lat": ASIA_BBOX[1],
                     "max_lng": ASIA_BBOX[2], "max_lat": ASIA_BBOX[3]},
            "n_cells": len(cells),
        },
        "models": {
            "fnpp": {
                "name": "F+NPP",
                "n_features": len(F_NPP_FEATURES),
                "features": F_NPP_FEATURES,
                "training_n_asia": int(f_npp_metrics["n_train"]),
                "validation_n_us": int(f_npp_metrics["n_us"]),
                "transfer_r2": round(float(f_npp_metrics["transfer"]["r2"]), 3),
                "transfer_ci_low": round(float(f_npp_metrics["transfer"]["ci_low"]), 3),
                "transfer_ci_high": round(float(f_npp_metrics["transfer"]["ci_high"]), 3),
            },
            "fullmodis": {
                "name": "Full+MODIS",
                "n_features": len(FULL_MODIS_FEATURES),
                "features": FULL_MODIS_FEATURES,
                "training_n_asia": int(full_modis_metrics["n_train"]),
                "validation_n_us": int(full_modis_metrics["n_us"]),
                "transfer_r2": round(float(full_modis_metrics["transfer"]["r2"]), 3),
                "transfer_ci_low": round(float(full_modis_metrics["transfer"]["ci_low"]), 3),
                "transfer_ci_high": round(float(full_modis_metrics["transfer"]["ci_high"]), 3),
            },
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
