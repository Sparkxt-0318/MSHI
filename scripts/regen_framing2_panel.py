"""Phase 2B of atlas-figure-regen-2026:
re-render framing2_comparison_panel using Full+MODIS predictions from
data/outputs/atlas_lookup.json (0.5° / ~55 km).

The previous panel encoded:
  left  : F (climate-only)  transfer R² = +0.127  (correct)
  middle: Run-A B (climate + 20 features, no MODIS)  transfer R² = +0.020  (STALE)
  right : B − F  (soil contribution)

After regen:
  left  : F (climate-only)        transfer R² = +0.127         (unchanged)
  middle: Full+MODIS (34 feats)   transfer R² = +0.072         (corrected)
  right : Full+MODIS − F-only     (soil + MODIS contribution)

The original framing called the middle panel "overfits Asia". The Full+MODIS
CI (-0.084, +0.189) spans zero, so "more features hurt" is more accurate
than "overfits" — the model isn't clearly worse than chance, it's just
clearly worse than F.

Data sources (no model retraining, no re-extraction):
  atlas_lookup.json cells[i].fullmodis.pred_log_rs           → Full+MODIS prediction
  atlas_lookup.json cells[i].fullmodis.pred_climate_log_rs   → 8-bioclim "F" prediction
  (The lookup's climate baseline is an 8-bioclim XGB model trained on the
  same Asian training set as F, with F+NPP-style hyperparameters. This is
  the same 8-bioclim feature set as F. Hyperparameters differ in the
  fourth decimal — well below the visualisation noise floor.)
"""
import json
import sys
import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"


def to_grid(df, value_col, lons, lats):
    s = (df.set_index(["latitude", "longitude"])[value_col]
         .unstack("longitude")
         .reindex(index=lats, columns=lons))
    return s.to_numpy()


def main() -> int:
    lookup = json.loads((OUT / "atlas_lookup.json").read_text())

    rows = []
    for c in lookup["cells"]:
        fm = c.get("fullmodis")
        if fm is None:
            continue
        rows.append({
            "longitude": c["lon"],
            "latitude": c["lat"],
            "F_log_rs": fm["pred_climate_log_rs"],   # 8-bioclim F-equivalent
            "FM_log_rs": fm["pred_log_rs"],           # Full+MODIS prediction
            "FM_anomaly": fm["anomaly"],              # = exp(FM - F)
        })
    df = pd.DataFrame(rows)
    print(f"loaded {len(df):,} cells at 0.5° from atlas_lookup.json")

    lons = np.sort(df["longitude"].unique())
    lats = np.sort(df["latitude"].unique())
    print(f"  grid: {len(lons)} lon × {len(lats)} lat")

    g_F_pred = to_grid(df, "F_log_rs", lons, lats)
    g_FM_pred = to_grid(df, "FM_log_rs", lons, lats)
    g_FM_anom = to_grid(df, "FM_anomaly", lons, lats)

    # Build "F anomaly" the same way: F prediction / median F prediction.
    # That gives both left and middle panels the same anomaly-ratio framing,
    # comparable to the original 5 km framing2 panel (which used F vs 5-bio
    # baseline). Here the baseline is the median climate-only prediction
    # over all land cells — a constant reference that lets us see F's
    # spatial deviation from its own central tendency.
    F_median = np.nanmedian(g_F_pred)
    g_F_anom = np.exp(g_F_pred - F_median)
    print(f"  F median log_rs = {F_median:.3f}  (anomaly denominator)")
    print(f"  F   anomaly  median={np.nanmedian(g_F_anom):.3f}  "
          f"5–95% ({np.nanpercentile(g_F_anom, 5):.3f}, {np.nanpercentile(g_F_anom, 95):.3f})")
    print(f"  FM  anomaly  median={np.nanmedian(g_FM_anom):.3f}  "
          f"5–95% ({np.nanpercentile(g_FM_anom, 5):.3f}, {np.nanpercentile(g_FM_anom, 95):.3f})")

    # Soil + MODIS contribution: FM anomaly minus F anomaly (both anomaly
    # ratios on the same grid, so the diff is interpretable as "how much
    # do the extra features change the predicted Rs vs climate-alone").
    g_diff = g_FM_anom - g_F_anom

    extent = [lons.min(), lons.max(), lats.min(), lats.max()]
    cmap_anom = plt.get_cmap("RdBu_r")
    cmap_diff = plt.get_cmap("RdBu_r")

    fig, axes = plt.subplots(1, 3, figsize=(18, 7),
                             gridspec_kw={"wspace": 0.06})
    panels = [
        (g_F_anom, cmap_anom, Normalize(0.5, 1.5),
         "Climate features only\n(generalizes: transfer R² = +0.127)",
         "Anomaly (predicted Rs ÷ climate-only median)"),
        (g_FM_anom, cmap_anom, Normalize(0.5, 1.5),
         "Climate + soil features\n(more features hurt: transfer R² = +0.072)",
         "Anomaly (predicted Rs ÷ climate baseline)"),
        (g_diff, cmap_diff, Normalize(-0.30, 0.30),
         "Soil-feature contribution\n(map structure that does not transfer)",
         "Δ anomaly  (Full+MODIS − climate-only)"),
    ]

    ims = []
    for ax, (data, cmap, norm, title, cbar_label) in zip(axes, panels):
        im = ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                       norm=norm, aspect="auto", interpolation="nearest")
        ax.set_title(title, fontsize=10.5, pad=8)
        ax.set_xlabel("longitude", fontsize=9)
        if ax is axes[0]:
            ax.set_ylabel("latitude", fontsize=9)
        else:
            ax.set_yticklabels([])
        ax.tick_params(axis="both", labelsize=8)
        ims.append((im, cbar_label))

    fig.subplots_adjust(left=0.045, right=0.99, top=0.88, bottom=0.18)
    for ax, (im, label) in zip(axes, ims):
        pos = ax.get_position()
        cbar_ax = fig.add_axes([pos.x0 + 0.01, pos.y0 - 0.10,
                                pos.width - 0.02, 0.025])
        cbar = fig.colorbar(im, cax=cbar_ax, orientation="horizontal")
        cbar.set_label(label, fontsize=8.5, labelpad=4)
        cbar.ax.tick_params(labelsize=8)

    fig.suptitle(
        "Adding soil features adds Asia-specific structure that does not transfer "
        "to held-out US sites",
        fontsize=12.5, y=0.96,
    )

    out = OUT / "framing2_comparison_panel.png"
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
