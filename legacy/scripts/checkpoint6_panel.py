"""Checkpoint 6 (partial) — methodology evolution panel.

What's possible without MODIS:
  Top row: F (climate-only, R²=+0.127), B (full features, R²=+0.020),
           placeholder "Climate + NPP — pending MODIS"
  Bottom row: Köppen C anomaly, Köppen D anomaly, caption block

The Köppen panels show per-zone F-trained predictions over the
Asia 5km grid, masked to cells in that Köppen zone. Anomaly =
exp(F_pred − climate_baseline_pred) using the zone-specific training
subset. Cells outside the zone are NaN.

Output:
  data/outputs/methodology_evolution_panel.png       (300 DPI print)
  data/outputs/methodology_evolution_panel_screen.png (160 DPI deck)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle
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
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
PARAMS_CB = dict(n_estimators=400, max_depth=4, learning_rate=0.05,
                 subsample=0.85, n_jobs=1, verbosity=0)


def fit_predict_grid(asia_subset, grid_subset, full_feats, climate_feats):
    """Train F + climate baseline on asia_subset, predict on grid_subset, return anomaly."""
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
    asia = pd.read_parquet(PROC / "training_features.parquet")
    grid = pd.read_parquet(PROC / "asia_grid_5km.parquet")
    print(f"asia n={len(asia)}, grid n={len(grid)}")

    asia["koppen"] = asia.apply(koppen_class, axis=1)
    grid["koppen"] = grid.apply(koppen_class, axis=1)
    print("Asia Köppen counts:", asia["koppen"].value_counts().to_dict())
    print("Grid Köppen counts:", grid["koppen"].value_counts().to_dict())

    lons = np.sort(grid["longitude"].unique())
    lats = np.sort(grid["latitude"].unique())
    ny, nx = len(lats), len(lons)

    # ── Load existing F and B anomaly maps ──────────────────────────────────
    F_anom_df = pd.read_parquet(PROC / "hero_climate_only_asia_anomaly.parquet")
    B_anom_df = pd.read_parquet(PROC / "hero_full_features_asia_anomaly.parquet")

    def to2d(df, col):
        return (df.set_index(["latitude", "longitude"])[col]
                .unstack("longitude")
                .reindex(index=lats, columns=lons)
                .to_numpy())

    g_F = to2d(F_anom_df, "mshi_geo_anomaly")
    g_B = to2d(B_anom_df, "mshi_geo_anomaly")

    # ── Köppen-zone anomaly maps ────────────────────────────────────────────
    g_C = np.full((ny, nx), np.nan, dtype="float32")
    g_D = np.full((ny, nx), np.nan, dtype="float32")

    for zone, target_grid in [("C", g_C), ("D", g_D)]:
        a_zone = asia[asia["koppen"] == zone]
        g_zone = grid[grid["koppen"] == zone].copy()
        if len(g_zone) == 0 or len(a_zone) < 80:
            print(f"Köppen {zone}: skipping (asia n={len(a_zone)}, grid n={len(g_zone)})")
            continue
        print(f"Köppen {zone}: training F on n_asia={len(a_zone)}, predicting on n_grid={len(g_zone)}")
        anom = fit_predict_grid(a_zone, g_zone, CLIMATE_8, CLIMATE_5)
        # Place into the full ny×nx grid using the longitude/latitude index
        df_anom = pd.DataFrame({
            "longitude": g_zone["longitude"].to_numpy(),
            "latitude": g_zone["latitude"].to_numpy(),
            "anom": anom,
        })
        df_anom = df_anom.set_index(["latitude", "longitude"])["anom"]
        # Map indexed values back to (ny,nx) — efficient via dict
        lat_to_row = {v: i for i, v in enumerate(lats)}
        lon_to_col = {v: i for i, v in enumerate(lons)}
        for (la, lo), v in df_anom.items():
            target_grid[lat_to_row[la], lon_to_col[lo]] = v

    # ── Build the panel ─────────────────────────────────────────────────────
    extent = [lons.min(), lons.max(), lats.min(), lats.max()]
    cmap = plt.get_cmap("RdBu_r")
    norm = Normalize(0.5, 1.5)

    fig, axes = plt.subplots(2, 3, figsize=(18, 11),
                             gridspec_kw={"wspace": 0.10, "hspace": 0.30})

    panels = [
        # row 0
        ("F: Climate-only (8 bioclim)",
         "Transfer R² = +0.127  95% CI (+0.019, +0.216)\nstatistically significant",
         g_F, axes[0, 0], "map"),
        ("B: Full features (20)",
         "Transfer R² = +0.020  95% CI (-0.141, +0.146)\nstatistically indistinguishable from zero",
         g_B, axes[0, 1], "map"),
        ("Climate + NPP (12 features)",
         "PENDING MODIS export.\nF+NPP test cannot run until MODIS\nNPP raster lands at\ndata/raw/modis/npp_2020_2024_mean.tif.\nSee RUN_B_BLOCKERS.md.",
         None, axes[0, 2], "placeholder"),
        # row 1
        ("Köppen C (temperate)",
         "Per-zone F model on Asia C → US C\nTransfer R² = -0.336  CI (-1.06, +0.04)\nCI spans zero — fails",
         g_C, axes[1, 0], "map"),
        ("Köppen D (continental)",
         "Per-zone F model on Asia D → US D\nTransfer R² = -0.199  CI (-0.39, -0.06)\nCI below zero — significantly worse",
         g_D, axes[1, 1], "map"),
        ("Narrative",
         (None,),
         None, axes[1, 2], "caption"),
    ]

    for title, subtitle, data, ax, kind in panels:
        if kind == "map":
            ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                      norm=norm, aspect="auto", interpolation="nearest")
            ax.set_title(title, fontsize=11, fontweight="bold", pad=4)
            ax.text(0.5, -0.18, subtitle, transform=ax.transAxes,
                    ha="center", va="top", fontsize=8.5, color="#3A4048")
            ax.set_xlabel("longitude", fontsize=8)
            ax.set_ylabel("latitude", fontsize=8)
            ax.tick_params(labelsize=7)
        elif kind == "placeholder":
            ax.set_facecolor("#F8F4EE")
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_edgecolor("#C8CCD2")
                spine.set_linewidth(0.6)
            ax.set_title(title, fontsize=11, fontweight="bold",
                         color="#A4221A", pad=4)
            ax.text(0.5, 0.5, subtitle, transform=ax.transAxes,
                    ha="center", va="center", fontsize=10,
                    color="#3A4048", style="italic")
        elif kind == "caption":
            ax.set_facecolor("#FAF8F5")
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            narrative = (
                "Methodology evolution\n"
                "(Run-B partial; MODIS pending)\n"
                "\n"
                "(1) F: climate alone transfers Asia → US\n"
                "    (R² = +0.127, p < 0.05).\n"
                "\n"
                "(2) B: adding 12 SoilGrids and engineered\n"
                "    soil features collapses transfer to\n"
                "    R² = +0.020 (CI includes zero).\n"
                "\n"
                "(3) Climate + NPP — PENDING MODIS export.\n"
                "    Expected to lift R² but magnitude on\n"
                "    held-out cross-continent is unknown.\n"
                "\n"
                "(4) Köppen C (temperate): within-zone F\n"
                "    transfer fails. R² = -0.336, CI spans 0.\n"
                "\n"
                "(5) Köppen D (continental): within-zone F\n"
                "    transfer significantly worse than mean.\n"
                "    R² = -0.199, CI fully below zero.\n"
                "\n"
                "Climate-zone stratification does NOT rescue\n"
                "transfer — small per-zone training sets\n"
                "lose the cross-zone precipitation gradient\n"
                "that is the actual transferable signal.\n"
                "\n"
                "Pending: IGBP land-cover stratification\n"
                "(blocked on MODIS). The biosensor case for\n"
                "ground-truth measurement at the centimetre\n"
                "scale stands."
            )
            ax.text(0.04, 0.97, narrative, transform=ax.transAxes,
                    ha="left", va="top", fontsize=9.5,
                    color="#0E1116", linespacing=1.4,
                    family="sans-serif")

    # Single shared colorbar across the bottom of the row of maps
    fig.subplots_adjust(left=0.05, right=0.97, top=0.93, bottom=0.10)
    cbar_ax = fig.add_axes([0.10, 0.045, 0.55, 0.020])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Anomaly  (predicted Rs ÷ climate baseline)  —  shared across map panels",
                   fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    fig.suptitle(
        "MSHI-Geo methodology evolution — Asia → US transfer testing",
        fontsize=14, fontweight="bold", y=0.985,
    )

    out_print = OUT / "methodology_evolution_panel.png"
    out_screen = OUT / "methodology_evolution_panel_screen.png"
    fig.savefig(out_print, dpi=300, facecolor="white")
    fig.savefig(out_screen, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"→ {out_print}")
    print(f"→ {out_screen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
