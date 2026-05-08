"""Item 1 Checkpoint 6 (part 2) — methodology evolution panel v2.

Replaces the Run-B panel's MODIS-pending placeholder with the real
F+NPP and Full+MODIS anomaly maps. 2 × 3 grid:

  Row 1 (model evolution):    F   ·  F+NPP  ·  Full+MODIS
  Row 2 (stratification + narrative):  Köppen C  ·  Köppen D  ·  Caption

All maps share RdBu_r 0.5-1.5 anomaly colormap; one shared horizontal
colorbar across the bottom of the model-evolution row.

Output:
  data/outputs/methodology_evolution_panel_v2.png       (300 DPI)
  data/outputs/methodology_evolution_panel_v2_screen.png (160 DPI)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.checkpoint5_koppen import koppen_class  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "outputs"

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
CLIMATE_5 = ["bio01", "bio04", "bio12", "bio14", "bio15"]
TARGET = "log_rs_annual"

PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=2, verbosity=0)
PARAMS_CB = dict(n_estimators=400, max_depth=4, learning_rate=0.05,
                 subsample=0.85, n_jobs=2, verbosity=0)


def fit_predict_grid(asia_subset, grid_subset, full_feats, climate_feats):
    a = asia_subset.dropna(subset=[TARGET] + full_feats).reset_index(drop=True)
    if len(a) < 30:
        return None
    m_f = xgb.XGBRegressor(**PARAMS_F)
    m_f.fit(a[full_feats].to_numpy("float32"), a[TARGET].to_numpy("float32"))
    m_cb = xgb.XGBRegressor(**PARAMS_CB)
    m_cb.fit(a[climate_feats].to_numpy("float32"), a[TARGET].to_numpy("float32"))

    valid = grid_subset[full_feats].notna().all(axis=1).to_numpy()
    log_f = np.full(len(grid_subset), np.nan, dtype="float32")
    log_cb = np.full(len(grid_subset), np.nan, dtype="float32")
    if valid.any():
        log_f[valid] = m_f.predict(grid_subset.loc[valid, full_feats].to_numpy("float32"))
        log_cb[valid] = m_cb.predict(grid_subset.loc[valid, climate_feats].to_numpy("float32"))
    return np.exp(log_f - log_cb)


def main() -> int:
    print("Loading grids and existing anomaly maps...")
    grid_v1 = pd.read_parquet(PROC / "asia_grid_5km.parquet")
    grid_v2 = pd.read_parquet(PROC / "asia_grid_5km_v2.parquet")
    asia = pd.read_parquet(PROC / "training_features_v2.parquet")

    lons = np.sort(grid_v2["longitude"].unique())
    lats = np.sort(grid_v2["latitude"].unique())
    ny, nx = len(lats), len(lons)

    F_anom_df = pd.read_parquet(PROC / "hero_climate_only_asia_anomaly.parquet")
    FNPP_anom_df = pd.read_parquet(PROC / "hero_climate_npp_asia_anomaly.parquet")

    def to2d(df, col):
        return (df.set_index(["latitude", "longitude"])[col]
                .unstack("longitude")
                .reindex(index=lats, columns=lons)
                .to_numpy())

    g_F = to2d(F_anom_df, "mshi_geo_anomaly")
    g_FNPP = to2d(FNPP_anom_df, "mshi_geo_anomaly")

    # Cached Full+MODIS anomaly grid: skip the slow recompute if available.
    fm_cache = PROC / "asia_grid_5km_full_modis_anomaly.parquet"
    if fm_cache.exists():
        print(f"loading cached Full+MODIS anomaly from {fm_cache.name}")
        fm_df = pd.read_parquet(fm_cache)
        g_FM = (fm_df.set_index(["latitude", "longitude"])["anom"]
                .unstack("longitude")
                .reindex(index=lats, columns=lons)
                .to_numpy())
    else:
        print("Predicting Full+MODIS on grid (this is the slow step)...")
        SOIL = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec"]
        BIOCLIM = CLIMATE_8
        ENG = ["c_n_ratio", "clay_sand_ratio", "ph_optimality", "aridity_demartonne"]
        MODIS_CONT = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]

        if "landcover" not in grid_v2.columns:
            print("  sampling landcover at grid...")
            import rasterio
            with rasterio.open(ROOT / "data" / "raw" / "modis" / "landcover_igbp_2023.tif") as src:
                coords = list(zip(grid_v2["longitude"].to_numpy(),
                                  grid_v2["latitude"].to_numpy()))
                grid_v2["landcover"] = np.array([v[0] for v in src.sample(coords)],
                                                dtype="float64")

        asia_lc = asia["landcover"].dropna().astype("Int64")
        keep_classes = sorted(int(c) for c in asia_lc.value_counts()[asia_lc.value_counts() >= 10].index)
        LC_FEATS = [f"lc_{c:02d}" for c in keep_classes]
        FEATS_FM = SOIL + BIOCLIM + ENG + MODIS_CONT + LC_FEATS

        for c in keep_classes:
            asia[f"lc_{c:02d}"] = (asia["landcover"].astype("Int64") == c).astype("float32")
            grid_v2[f"lc_{c:02d}"] = (grid_v2["landcover"].astype("Int64") == c).astype("float32")

        PARAMS_FM = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                         subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
                         reg_alpha=2.0, reg_lambda=8.0, n_jobs=2, verbosity=0)
        a = asia.dropna(subset=[TARGET] + FEATS_FM).reset_index(drop=True)
        m_fm = xgb.XGBRegressor(**PARAMS_FM)
        m_fm.fit(a[FEATS_FM].to_numpy("float32"), a[TARGET].to_numpy("float32"))
        m_cb = xgb.XGBRegressor(**PARAMS_CB)
        m_cb.fit(a[CLIMATE_5].to_numpy("float32"), a[TARGET].to_numpy("float32"))

        valid_fm = grid_v2[FEATS_FM].notna().all(axis=1).to_numpy()
        valid_cb = grid_v2[CLIMATE_5].notna().all(axis=1).to_numpy()
        log_fm = np.full(len(grid_v2), np.nan, dtype="float32")
        log_cb = np.full(len(grid_v2), np.nan, dtype="float32")
        chunk = 500_000
        idx_fm = np.where(valid_fm)[0]
        idx_cb = np.where(valid_cb)[0]
        for s in range(0, len(idx_fm), chunk):
            sl = idx_fm[s:s + chunk]
            log_fm[sl] = m_fm.predict(grid_v2.iloc[sl][FEATS_FM].to_numpy("float32"))
        for s in range(0, len(idx_cb), chunk):
            sl = idx_cb[s:s + chunk]
            log_cb[sl] = m_cb.predict(grid_v2.iloc[sl][CLIMATE_5].to_numpy("float32"))
        g_FM_anom = np.exp(log_fm - log_cb)
        # Cache it for fast re-renders
        pd.DataFrame({
            "longitude": grid_v2["longitude"], "latitude": grid_v2["latitude"],
            "anom": g_FM_anom,
        }).to_parquet(fm_cache, index=False)
        g_FM = (pd.DataFrame({
            "longitude": grid_v2["longitude"], "latitude": grid_v2["latitude"],
            "anom": g_FM_anom,
        }).set_index(["latitude", "longitude"])["anom"]
        .unstack("longitude").reindex(index=lats, columns=lons).to_numpy())
        print(f"  Full+MODIS anomaly: median={np.nanmedian(g_FM_anom):.3f}, "
              f"valid frac={np.isfinite(g_FM_anom).mean()*100:.1f}%")

    # Köppen panels (re-use Run B's recipe on grid_v1 since grid_v1 has the
    # bioclim columns Köppen needs)
    print("Computing Köppen C and D anomaly maps...")
    asia["koppen"] = asia.apply(koppen_class, axis=1)
    grid_v1["koppen"] = grid_v1.apply(koppen_class, axis=1)

    g_C = np.full((ny, nx), np.nan, dtype="float32")
    g_D = np.full((ny, nx), np.nan, dtype="float32")
    lat_to_row = {v: i for i, v in enumerate(lats)}
    lon_to_col = {v: i for i, v in enumerate(lons)}

    for zone, target_grid in [("C", g_C), ("D", g_D)]:
        a_zone = asia[asia["koppen"] == zone]
        g_zone = grid_v1[grid_v1["koppen"] == zone].copy()
        if len(a_zone) < 80 or len(g_zone) == 0:
            continue
        anom = fit_predict_grid(a_zone, g_zone, CLIMATE_8, CLIMATE_5)
        df_anom = pd.DataFrame({
            "longitude": g_zone["longitude"].to_numpy(),
            "latitude": g_zone["latitude"].to_numpy(),
            "anom": anom,
        }).set_index(["latitude", "longitude"])["anom"]
        for (la, lo), v in df_anom.items():
            target_grid[lat_to_row[la], lon_to_col[lo]] = v

    print("Building panel...")
    extent = [lons.min(), lons.max(), lats.min(), lats.max()]
    cmap = plt.get_cmap("RdBu_r")
    norm = Normalize(0.5, 1.5)

    fig, axes = plt.subplots(2, 3, figsize=(18, 12),
                             gridspec_kw={"wspace": 0.10, "hspace": 0.42})

    panels = [
        # row 0 (top): subtitle goes BELOW the map (after xlabel)
        ("F: Climate-only (8 bioclim)",
         "Transfer R² = +0.127   CI (+0.019, +0.216)   ✓ statistically significant",
         g_F, axes[0, 0], "top_map"),
        ("F+NPP: + 4 MODIS continuous",
         "Transfer R² = +0.145   CI (+0.026, +0.241)   ★ best of any config",
         g_FNPP, axes[0, 1], "top_map"),
        ("Full+MODIS: 34 features",
         "Transfer R² = +0.072   CI (-0.084, +0.189)   CV jumps but transfer CI spans 0",
         g_FM, axes[0, 2], "top_map"),
        # row 1 (bottom): subtitle absorbed into multi-line title ABOVE the map
        ("Köppen C (temperate)",
         "Per-zone F   R² = -0.336   CI (-1.06, +0.04)   ✗ spans 0",
         g_C, axes[1, 0], "bottom_map"),
        ("Köppen D (continental)",
         "Per-zone F   R² = -0.199   CI (-0.39, -0.06)   ✗ significantly worse",
         g_D, axes[1, 1], "bottom_map"),
        ("Narrative",
         None, None, axes[1, 2], "caption"),
    ]

    for title, subtitle, data, ax, kind in panels:
        if kind == "top_map":
            ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                      norm=norm, aspect="auto", interpolation="nearest")
            ax.set_title(title, fontsize=11.5, fontweight="bold", pad=6)
            ax.set_xlabel("longitude", fontsize=8)
            ax.set_ylabel("latitude", fontsize=8)
            ax.tick_params(labelsize=7)
            # Subtitle sits directly beneath the xlabel, attached to this axes.
            ax.text(0.5, -0.27, subtitle, transform=ax.transAxes,
                    ha="center", va="top", fontsize=9, color="#3A4048")
        elif kind == "bottom_map":
            ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                      norm=norm, aspect="auto", interpolation="nearest")
            # Multi-line title puts the metric ABOVE the map as a subtitle line.
            ax.set_title(f"{title}\n{subtitle}",
                         fontsize=11.5, fontweight="bold", pad=6,
                         linespacing=1.4)
            ax.set_xlabel("longitude", fontsize=8)
            ax.set_ylabel("latitude", fontsize=8)
            ax.tick_params(labelsize=7)
            # Override the second line of the multi-line title to a smaller weight
            # by re-creating the title with two ax.text calls instead.
            ax.set_title("")
            ax.text(0.5, 1.10, title, transform=ax.transAxes,
                    ha="center", va="bottom", fontsize=11.5, fontweight="bold")
            ax.text(0.5, 1.04, subtitle, transform=ax.transAxes,
                    ha="center", va="bottom", fontsize=9, color="#3A4048")
        elif kind == "caption":
            ax.set_facecolor("#FAF8F5")
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.text(0.5, 0.85,
                    "Item 1 take-aways",
                    transform=ax.transAxes, ha="center", va="top",
                    fontsize=14, fontweight="bold", color="#0E1116")
            lines = [
                "F+NPP is the new headline\n(transfer R² +0.145, NPP rank-1 SHAP)",
                "Full+MODIS rescues CV but not transfer\n(soil-feature confound persists)",
                "Köppen stratification fails —\nbiosensor argument stands",
            ]
            ys = [0.65, 0.45, 0.25]
            for y, line in zip(ys, lines):
                ax.text(0.06, y, "•", transform=ax.transAxes,
                        ha="left", va="center",
                        fontsize=20, color="#A4221A", fontweight="bold")
                ax.text(0.13, y, line, transform=ax.transAxes,
                        ha="left", va="center",
                        fontsize=12.5, color="#0E1116", linespacing=1.35)

    # Bottom margin must clear: the bottom map titles AND the colorbar.
    fig.subplots_adjust(left=0.045, right=0.99, top=0.92, bottom=0.085)
    cbar_ax = fig.add_axes([0.18, 0.025, 0.50, 0.018])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Anomaly  (predicted Rs ÷ climate baseline)",
                   fontsize=9.5, color="#0E1116", labelpad=4)
    cbar.ax.tick_params(labelsize=9, colors="#3A4048")

    fig.suptitle(
        "MSHI-Geo methodology evolution — Asia → US transfer testing  (v2: MODIS integrated)",
        fontsize=14, fontweight="bold", y=0.985,
    )

    fig.savefig(OUT / "methodology_evolution_panel_v2.png", dpi=300,
                facecolor="white")
    fig.savefig(OUT / "methodology_evolution_panel_v2_screen.png", dpi=160,
                facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT/'methodology_evolution_panel_v2.png'}")
    print(f"wrote {OUT/'methodology_evolution_panel_v2_screen.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
