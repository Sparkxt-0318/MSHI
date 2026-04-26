"""Task 4 — render two hero maps (climate-only and full-features) plus a
side-by-side comparison panel.

Pipeline:
  1. Train F_climate_only and B_heavier_reg models on the Asia training set.
  2. Train the 5-bio climate baseline (same as composite.py / climate_baseline).
  3. Predict each model on the 5km Asia grid; compute anomaly = exp(full) / exp(climate).
  4. Save two anomaly parquets and run hero_map.render_hero_map for each.
  5. Build a 3-panel comparison: (climate-only, full-features, full−climate diff).

Honest framing: F is the only config with non-zero transfer R²; B's hero
visualises a model whose extra soil signal does NOT generalise out of Asia,
but the full-Asia map is still legible because the 5-bio climate baseline
in the denominator carries most of the structure.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hero_map import render_hero_map  # noqa: E402

OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"

TARGET = "log_rs_annual"

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
CLIMATE_5_BASELINE = ["bio01", "bio04", "bio12", "bio14", "bio15"]
ALL_FEATS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec",
             *CLIMATE_8, "c_n_ratio", "clay_sand_ratio", "ph_optimality",
             "aridity_demartonne"]

PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
PARAMS_B = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=8,
                reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)
PARAMS_CB = dict(n_estimators=400, max_depth=4, learning_rate=0.05,
                 subsample=0.85, n_jobs=1, verbosity=0)


def fit(feats, params, train, target_col):
    df = train.dropna(subset=[target_col] + feats).reset_index(drop=True)
    m = xgb.XGBRegressor(**params)
    m.fit(df[feats].to_numpy("float32"), df[target_col].to_numpy("float32"))
    return m


def predict_chunked(model, feats, grid, chunk=200_000):
    out = np.full(len(grid), np.nan, dtype="float32")
    valid = grid[feats].notna().all(axis=1).to_numpy()
    idx = np.where(valid)[0]
    for s in range(0, len(idx), chunk):
        sl = idx[s:s + chunk]
        out[sl] = model.predict(grid.iloc[sl][feats].to_numpy("float32"))
    return out


def main() -> int:
    train = pd.read_parquet(PROC / "training_features.parquet")
    grid = pd.read_parquet(PROC / "asia_grid_5km.parquet")
    print(f"train rows: {len(train)},  grid cells: {len(grid)}")

    # 1. Train both 'full' models + the climate baseline
    print("training F_climate_only ...")
    model_F = fit(CLIMATE_8, PARAMS_F, train, TARGET)
    print("training B_heavier_reg (20 features) ...")
    model_B = fit(ALL_FEATS, PARAMS_B, train, TARGET)
    print("training 5-bio climate baseline ...")
    model_cb = fit(CLIMATE_5_BASELINE, PARAMS_CB, train, TARGET)

    # 2. Predict on grid
    print("predicting climate-only ...")
    log_F = predict_chunked(model_F, CLIMATE_8, grid)
    print("predicting full-features ...")
    log_B = predict_chunked(model_B, ALL_FEATS, grid)
    print("predicting 5-bio climate baseline ...")
    log_cb = predict_chunked(model_cb, CLIMATE_5_BASELINE, grid)

    # 3. Anomalies (clamp to a sensible range so colourmap doesn't blow up)
    anom_F = np.exp(log_F - log_cb)
    anom_B = np.exp(log_B - log_cb)
    print(f"anom_F  median={np.nanmedian(anom_F):.3f}  IQR=({np.nanquantile(anom_F,.25):.3f},{np.nanquantile(anom_F,.75):.3f})")
    print(f"anom_B  median={np.nanmedian(anom_B):.3f}  IQR=({np.nanquantile(anom_B,.25):.3f},{np.nanquantile(anom_B,.75):.3f})")

    # 4. Build per-hero parquets & render
    base = grid[["longitude", "latitude"]].copy()
    df_F = base.copy(); df_F["mshi_geo_anomaly"] = anom_F
    df_B = base.copy(); df_B["mshi_geo_anomaly"] = anom_B

    for name, df, label in [
        ("hero_climate_only_asia", df_F, "Climate features only"),
        ("hero_full_features_asia", df_B, "Climate + soil features (overfits)"),
    ]:
        parquet_path = PROC / f"{name}_anomaly.parquet"
        df.to_parquet(parquet_path, index=False)
        print(f"  rendering {name} ...")
        # Use the existing hero_map renderer, then we'll annotate by writing a
        # subtitle into the figure file via a small post-process. The renderer
        # already takes metadata; we can pass the label through a custom key
        # (it's just shown in the metadata strip).
        render_hero_map(
            df,
            OUT / f"{name}.png",
            OUT / f"{name}.pdf",
            OUT / f"{name}_screen.png",
            metadata={
                "cv_r2": "—",
                "transfer_r2": "—",
                "n_train": int(len(train)),
                "n_us": "—",
                "resolution_km": "~5",
                "subtitle": label,
            },
        )

    # 5. Comparison panel — 3 subplots: F, B, B−F (difference)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    # Reshape to 2-D grids
    lons = np.sort(grid["longitude"].unique())
    lats = np.sort(grid["latitude"].unique())
    ny, nx = len(lats), len(lons)

    def to2d(v):
        return v.reshape(ny, nx)

    g_F = to2d(anom_F)
    g_B = to2d(anom_B)
    g_diff = g_B - g_F  # +ve = full predicts more Rs than climate-only

    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5),
                             gridspec_kw={"wspace": 0.10})
    extent = [lons.min(), lons.max(), lats.min(), lats.max()]
    cmap_anom = plt.get_cmap("RdBu")
    cmap_diff = plt.get_cmap("PuOr_r")
    panels = [
        (g_F,    cmap_anom, Normalize(0.5, 1.5), "F: Climate-only\n(Transfer R² = +0.127)",        "Anomaly  (full / climate baseline)"),
        (g_B,    cmap_anom, Normalize(0.5, 1.5), "B: Full features (20)\n(Transfer R² = +0.020)", "Anomaly"),
        (g_diff, cmap_diff, Normalize(-0.30, 0.30),  "B − F\n(soil-feature contribution)",        "Δ anomaly (B − F)"),
    ]
    for ax, (data, cmap, norm, title, cbar_label) in zip(axes, panels):
        im = ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                       norm=norm, aspect="auto")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        cbar = plt.colorbar(im, ax=ax, fraction=0.034, pad=0.04)
        cbar.set_label(cbar_label, fontsize=8)

    fig.suptitle("Framing-2 comparison — soil features add Asia-specific structure that "
                 "does not transfer to held-out US",
                 fontsize=12, y=1.00)
    out = OUT / "framing2_comparison_panel.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  → {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
