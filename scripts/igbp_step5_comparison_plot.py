"""IGBP-fallback Step 5 — visual comparison of stratification approaches.

Produces a forest-plot-style figure:
  • Cross-biome F baseline (R² = +0.127, CI excludes 0)
  • Köppen-Geiger zones (Run B): C, D
  • IGBP biomes (this run): forest, savanna, grassland, cropland

X-axis: transfer R². Each row is a stratum, with point estimate +
95% bootstrap CI as horizontal bars. Color codes whether the CI
excludes zero.

Output: data/outputs/stratification_comparison.png (300 DPI + 160 DPI
screen).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"

# Bedrock palette
C = {
    "paper":    "#FAF8F5",
    "ink":      "#0E1116",
    "ink_soft": "#3A4048",
    "rule":     "#C8CCD2",
    "accent":   "#A4221A",
    "blue":     "#1F4068",
}

# Load bootstraps
ci = json.load(open(OUT / "bootstrap_ci.json"))
kop = json.load(open(OUT / "koppen_stratification.json"))
igbp = json.load(open(OUT / "igbp_stratification.json"))

F_ = ci["F_climate_only"]

# Build the rows (label, n_us, R², ci_low, ci_high, ci_excludes_zero, group)
rows = []

rows.append(("F baseline (cross-biome)", F_["n_us"],
             F_["median"], F_["ci_low"], F_["ci_high"],
             F_["ci_excludes_zero"], "baseline"))

# Run B Köppen
for zone in ["C", "D"]:
    z = kop["results"][zone]
    if z.get("skipped"):
        continue
    rows.append((f"Köppen {zone}",
                 z["n_us"], z["transfer_r2"],
                 z["ci_low"], z["ci_high"],
                 z["ci_excludes_zero"],
                 "koppen"))

# Item 1 IGBP
for biome in ["forest", "savanna", "grassland", "cropland"]:
    b = igbp["results"][biome]
    if b.get("skipped"):
        continue
    rows.append((f"IGBP {biome}",
                 b["n_us"], b["transfer_r2"],
                 b["ci_low"], b["ci_high"],
                 b["ci_excludes_zero"],
                 "igbp"))

# Plot
fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=C["paper"])

y_positions = np.arange(len(rows))[::-1]  # baseline at top
labels = [r[0] for r in rows]

for y, (label, n_us, r2, lo, hi, excl, group) in zip(y_positions, rows):
    # Color by group
    if group == "baseline":
        color = C["accent"]; lw_pt = 2.4; ms = 11
    elif group == "koppen":
        color = C["blue"]; lw_pt = 1.6; ms = 8
    else:
        color = C["ink"]; lw_pt = 1.6; ms = 8

    # CI bar
    ax.plot([lo, hi], [y, y], color=color, linewidth=2.0, solid_capstyle="round",
            alpha=0.85)
    ax.plot([lo, lo], [y - 0.15, y + 0.15], color=color, lw=lw_pt)
    ax.plot([hi, hi], [y - 0.15, y + 0.15], color=color, lw=lw_pt)
    # Point estimate
    marker_face = color if excl else "white"
    ax.plot(r2, y, "o", color=color, markersize=ms,
            markerfacecolor=marker_face, markeredgewidth=1.6)
    # Annotation: n and R²
    annotation = f"  n_us = {n_us}   R² = {r2:+.3f}"
    if excl:
        annotation += "   (excl. 0)"
    ax.annotate(annotation, xy=(hi + 0.02, y), xytext=(0, 0),
                textcoords="offset points",
                fontsize=8.5, color=C["ink_soft"], va="center")

# Vertical zero line
ax.axvline(0, color=C["ink_soft"], lw=0.8, alpha=0.6, linestyle="--")

ax.set_yticks(y_positions)
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel("Asia → US transfer R²", fontsize=11, color=C["ink"])
ax.set_title("Stratification does not rescue cross-continental Rs transfer",
             fontsize=13, color=C["ink"], weight="bold", pad=14, loc="left")
ax.set_xlim(-1.1, 0.65)
ax.tick_params(axis="x", labelsize=9, colors=C["ink_soft"])
ax.tick_params(axis="y", labelsize=10, colors=C["ink"])
ax.set_facecolor(C["paper"])
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
for s in ["left", "bottom"]:
    ax.spines[s].set_color(C["rule"])

# Legend (filled = CI excl 0; open = CI spans 0)
ax.text(0.99, 0.04,
        "Filled marker: 95% CI excludes 0   ·   Open marker: CI spans 0",
        transform=ax.transAxes, ha="right", va="bottom",
        fontsize=8, color=C["ink_soft"], style="italic")
ax.text(0.01, -0.18,
        f"Cross-biome F (8 bioclim) is the only configuration with a 95% CI on transfer R² that excludes zero. "
        f"Köppen C and D and IGBP savanna / grassland / cropland have CIs spanning zero "
        f"despite varied point estimates. IGBP forest's CI is fully BELOW zero (within-biome model does worse "
        f"than the US-mean predictor). Conclusion: neither climate-zone stratification nor land-cover "
        f"stratification recovers cross-continental Rs transfer at this sample size.",
        transform=ax.transAxes, ha="left", va="top",
        fontsize=8.5, color=C["ink"], wrap=True)

fig.subplots_adjust(left=0.18, right=0.97, top=0.93, bottom=0.27)
fig.savefig(OUT / "stratification_comparison.png", dpi=300,
            facecolor=C["paper"])
fig.savefig(OUT / "stratification_comparison_screen.png", dpi=160,
            facecolor=C["paper"])
plt.close(fig)
print(f"Wrote {OUT/'stratification_comparison.png'}")
print(f"Wrote {OUT/'stratification_comparison_screen.png'}")
