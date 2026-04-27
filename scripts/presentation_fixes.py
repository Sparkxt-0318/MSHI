"""Presentation fixes (no pipeline rerun):
  - Re-render hero_climate_only_asia with config-F metadata
  - Re-render hero_full_features_asia with config-B metadata
  - Rebuild framing2_comparison_panel.png with external colorbars,
    correct anomaly colorbar on middle panel, RdBu_r on diff panel,
    and the new titles/suptitle.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hero_map import render_hero_map  # noqa: E402

OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 + 2 — re-render heroes with full metadata
# ─────────────────────────────────────────────────────────────────────────────
common = dict(n_train=615, n_us=274, resolution_km="~5")

print("Fix 1: hero_climate_only_asia (config F)")
df_F = pd.read_parquet(PROC / "hero_climate_only_asia_anomaly.parquet")
render_hero_map(
    df_F,
    OUT / "hero_climate_only_asia.png",
    OUT / "hero_climate_only_asia.pdf",
    OUT / "hero_climate_only_asia_screen.png",
    metadata=dict(cv_r2=-0.067, transfer_r2=0.127, **common),
)

print("Fix 2: hero_full_features_asia (config B)")
df_B = pd.read_parquet(PROC / "hero_full_features_asia_anomaly.parquet")
render_hero_map(
    df_B,
    OUT / "hero_full_features_asia.png",
    OUT / "hero_full_features_asia.pdf",
    OUT / "hero_full_features_asia_screen.png",
    metadata=dict(cv_r2=-0.083, transfer_r2=0.020, **common),
)

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — rebuild comparison panel
# ─────────────────────────────────────────────────────────────────────────────
print("Fix 3: rebuilding framing2_comparison_panel.png")
grid = pd.read_parquet(PROC / "asia_grid_5km.parquet")
lons = np.sort(grid["longitude"].unique())
lats = np.sort(grid["latitude"].unique())
ny, nx = len(lats), len(lons)


def to_grid(df):
    """Turn a (lon,lat,mshi_geo_anomaly) df into a (ny,nx) array sorted asc."""
    s = (df.set_index(["latitude", "longitude"])["mshi_geo_anomaly"]
         .unstack("longitude")
         .reindex(index=lats, columns=lons))
    return s.to_numpy()


g_F = to_grid(df_F)
g_B = to_grid(df_B)
g_diff = g_B - g_F

fig, axes = plt.subplots(1, 3, figsize=(18, 7),
                         gridspec_kw={"wspace": 0.06})
extent = [lons.min(), lons.max(), lats.min(), lats.max()]
cmap_anom = plt.get_cmap("RdBu_r")
cmap_diff = plt.get_cmap("RdBu_r")  # same family for visual consistency

panels = [
    (g_F,    cmap_anom, Normalize(0.5, 1.5),
     "Climate features only\n(generalizes: transfer R² = +0.127)",
     "Anomaly (predicted Rs ÷ climate baseline)"),
    (g_B,    cmap_anom, Normalize(0.5, 1.5),
     "Climate + soil features\n(overfits Asia: transfer R² = +0.020)",
     "Anomaly (predicted Rs ÷ climate baseline)"),
    (g_diff, cmap_diff, Normalize(-0.30, 0.30),
     "Soil-feature contribution\n(map structure that does not transfer)",
     "Δ anomaly  (full − climate-only)"),
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

# External horizontal colorbars below each subplot
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
plt.savefig(out, dpi=160, facecolor="white")
plt.close(fig)
print(f"  → {out}")
print("done.")
