"""Round C-3 — conference poster via matplotlib, 36 × 24 in landscape PDF.

Falls back from the pptxgenjs-then-libreoffice path because libreoffice
on this host cannot import .pptx (Java not configured). matplotlib
renders the same Bedrock-styled poster directly to PDF.

Layout (36 × 24 in landscape):
  Header strip         — title, name, school, date, github URL
  Row 1 (3 cols)       — Problem, Methods, Three-tier framework
  Row 2 (2 cols)       — Hero map (left, wide), SHAP comparison (right)
  Row 3 (full width)   — Methodology evolution panel
  Row 4 (3 cols)       — Köppen finding, Sensor connection figure, Implications/refs
  Footer hairline rule

Outputs:
  data/outputs/genius_poster.pdf   (vector, print-ready)
  data/outputs/genius_poster.png   (raster preview, 100 DPI)
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle

OUT = Path("/home/user/MSHI/data/outputs")

# Bedrock palette
C = {
    "paper":    "#FAF8F5",
    "ink":      "#0E1116",
    "ink_soft": "#3A4048",
    "rule":     "#C8CCD2",
    "accent":   "#A4221A",
}
F = {"header": "Georgia", "body": "DejaVu Sans", "mono": "DejaVu Sans Mono"}

# ── Pull verified numbers ────────────────────────────────────────────
ci = json.load(open(OUT / "bootstrap_ci.json"))
alt = json.load(open(OUT / "alternative_metrics.json"))
kop = json.load(open(OUT / "koppen_stratification.json"))
F_ = ci["F_climate_only"]
B_ = ci["B_full_features"]
kopC = kop["results"]["C"]
kopD = kop["results"]["D"]


def add_text(ax, x, y, text, **kw):
    """Wrapper: text in ax-data coords (0-1), with sane defaults."""
    defaults = dict(transform=ax.transAxes, color=C["ink"],
                    family=kw.pop("family", F["body"]),
                    fontsize=kw.pop("fontsize", 11),
                    ha=kw.pop("ha", "left"),
                    va=kw.pop("va", "top"))
    defaults.update(kw)
    return ax.text(x, y, text, **defaults)


def col_panel(ax, eyebrow, title):
    ax.set_facecolor(C["paper"])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    add_text(ax, 0.0, 1.0, eyebrow, family=F["mono"], fontsize=11,
             color=C["accent"], weight="bold")
    add_text(ax, 0.0, 0.94, title, family=F["header"], fontsize=18,
             color=C["ink"], weight="bold", va="top")
    ax.plot([0.0, 1.0], [0.86, 0.86], color=C["rule"], lw=0.8,
            transform=ax.transAxes, clip_on=False)


def img_panel(ax, eyebrow, image_path, caption=None, image_h_frac=0.85):
    ax.set_facecolor(C["paper"])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    add_text(ax, 0.0, 1.0, eyebrow, family=F["mono"], fontsize=11,
             color=C["accent"], weight="bold")
    if image_path.exists():
        img = mpimg.imread(image_path)
        # Fit image to panel preserving aspect; we just stick it in axes coords
        # via inset_axes for cleaner layout
        ax.imshow(img, extent=(0.0, 1.0, 0.0, image_h_frac), aspect="auto")
    if caption:
        add_text(ax, 0.0, image_h_frac - 0.01, caption,
                 fontsize=9, color=C["ink"], va="top")


# ── Build the figure ─────────────────────────────────────────────────
fig = plt.figure(figsize=(36, 24), facecolor=C["paper"])

# Use gridspec for layout
gs = fig.add_gridspec(
    nrows=4, ncols=12,
    height_ratios=[2.4, 5.5, 6.5, 6.0],
    hspace=0.18, wspace=0.18,
    left=0.025, right=0.975, top=0.975, bottom=0.025,
)

# ── Header (full width) ──────────────────────────────────────────────
ax_h = fig.add_subplot(gs[0, :])
ax_h.set_facecolor(C["paper"]); ax_h.set_xlim(0, 1); ax_h.set_ylim(0, 1); ax_h.axis("off")
add_text(ax_h, 0.0, 0.95, "MSHI-GEO", family=F["mono"], fontsize=22,
         color=C["accent"], weight="bold")
add_text(ax_h, 0.0, 0.78,
         "Soil Microbial Respiration: A Three-Tier Monitoring Stack",
         family=F["header"], fontsize=42, color=C["ink"], weight="bold")
add_text(ax_h, 0.0, 0.20,
         "[Author Name]   ·   [School / Institution]   ·   Genius Olympiad 2026",
         family=F["mono"], fontsize=14, color=C["ink_soft"])
add_text(ax_h, 1.0, 0.95,
         "Published EAB sensor work\nMSHI-Geo manuscript queued for ESSD",
         family=F["body"], fontsize=12, color=C["ink"], ha="right",
         style="italic")
add_text(ax_h, 1.0, 0.20, "github.com/Sparkxt-0318/MSHI",
         family=F["mono"], fontsize=14, color=C["ink_soft"], ha="right")
ax_h.plot([0.0, 1.0], [0.10, 0.10], color=C["accent"], lw=2.4,
          transform=ax_h.transAxes, clip_on=False)

# ── Row 1: three columns ─────────────────────────────────────────────
ax_r1c1 = fig.add_subplot(gs[1, 0:4])
col_panel(ax_r1c1, "01  ·  PROBLEM",
          "Soil respiration has no high-resolution validator.")
add_text(ax_r1c1, 0.0, 0.78,
         "Soils release ~91 Pg C yr⁻¹ to the atmosphere — second only to ocean exchange. "
         "Continental Rs upscaling models (Hashimoto 2015; Warner 2019; Stell 2021) "
         "report uncertainty as Monte-Carlo CIs on the global sum, not as held-out "
         "site-level transfer.\n\n"
         "We characterise the cross-continental transfer gap directly: train an "
         "XGBoost on Asian Rs sites, test on a held-out US subset, report transfer "
         "R² with 2 000-iteration bootstrap CIs and ranked SHAP drivers per region. "
         "The result clarifies what the standard feature stack can and cannot do at "
         "this scale, and where ground-truth biosensor measurement is needed.",
         fontsize=12, va="top",
         wrap=True)

ax_r1c2 = fig.add_subplot(gs[1, 4:8])
col_panel(ax_r1c2, "02  ·  METHODS",
          "Open data, gradient-boosted trees, held-out continent.")
methods_text = (
    "Training data\n"
    "  615 Asia (605 SRDB v5 + 10 COSORE)\n"
    "  274 CONUS held-out (253 SRDB + 21 COSORE)\n"
    "  Target: log Rs_annual (g C m⁻² yr⁻¹)\n"
    "\n"
    "Features (20)\n"
    "  8 WorldClim 2.1 bioclim variables\n"
    "  8 SoilGrids 2.0 5-15 cm topsoil layers\n"
    "  4 engineered (C/N, clay/sand, pH-opt, aridity)\n"
    "\n"
    "Model & validation\n"
    "  XGBoost depth=3, n_est=250, regularised\n"
    "  5-fold spatial-block CV (5° blocks), Asia\n"
    "  Asia → US transfer R² + 2,000-iter bootstrap"
)
add_text(ax_r1c2, 0.0, 0.78, methods_text, fontsize=12, va="top",
         family=F["body"])

ax_r1c3 = fig.add_subplot(gs[1, 8:12])
col_panel(ax_r1c3, "03  ·  FRAMEWORK",
          "One biology, three scales of measurement.")
tiers = [
    (0.65, "cm", C["accent"], "Electrochemical biosensor",
     "Electron-transfer current ∝ substrate oxidation. Centimetre footprint, continuous, low cost."),
    (0.40, "m", C["ink_soft"], "Chamber + eddy-covariance",
     "Direct CO₂ flux measurement. Metre footprint, sparse, high instrument cost."),
    (0.15, "km", C["ink_soft"], "Satellite + ML upscaling (this work)",
     "5 km grid. Climate + soil features. Transfer-tested."),
]
for y, scale, col, name, desc in tiers:
    ax_r1c3.text(0.04, y, scale, transform=ax_r1c3.transAxes,
                 family=F["header"], fontsize=32, color=col, weight="bold",
                 va="center")
    ax_r1c3.text(0.20, y + 0.04, name, transform=ax_r1c3.transAxes,
                 family=F["header"], fontsize=14, color=C["ink"], weight="bold",
                 va="center")
    ax_r1c3.text(0.20, y - 0.06, desc, transform=ax_r1c3.transAxes,
                 family=F["body"], fontsize=9.5, color=C["ink_soft"], va="center")

# ── Row 2: hero map (8 cols) + SHAP comparison (4 cols) ──────────────
ax_r2c1 = fig.add_subplot(gs[2, 0:8])
ax_r2c1.set_facecolor(C["paper"]); ax_r2c1.set_xlim(0, 1); ax_r2c1.set_ylim(0, 1); ax_r2c1.axis("off")
add_text(ax_r2c1, 0.0, 1.0,
         "04  ·  HERO MAP — climate-only model on Asia (R² = +0.127, CI excludes 0)",
         family=F["mono"], fontsize=11, color=C["accent"], weight="bold")
hero_path = OUT / "hero_climate_only_asia.png"
if hero_path.exists():
    ax_inset = ax_r2c1.inset_axes([0.0, 0.0, 1.0, 0.94])
    img = mpimg.imread(hero_path)
    ax_inset.imshow(img, aspect="auto")
    ax_inset.axis("off")

ax_r2c2 = fig.add_subplot(gs[2, 8:12])
ax_r2c2.set_facecolor(C["paper"]); ax_r2c2.set_xlim(0, 1); ax_r2c2.set_ylim(0, 1); ax_r2c2.axis("off")
add_text(ax_r2c2, 0.0, 1.0,
         "05  ·  REGIONAL DRIVER HETEROGENEITY",
         family=F["mono"], fontsize=11, color=C["accent"], weight="bold")
shap_path = OUT / "shap_comparison.png"
if shap_path.exists():
    ax_inset = ax_r2c2.inset_axes([0.0, 0.20, 1.0, 0.74])
    img = mpimg.imread(shap_path)
    ax_inset.imshow(img, aspect="auto")
    ax_inset.axis("off")
add_text(ax_r2c2, 0.0, 0.18,
         "Same XGBoost trained separately on Asia and US. bio12 (annual precip) is "
         "the only feature with stable rank in both regions. clay/sand-ratio drops "
         "out of US top 8; nitrogen jumps to US rank 2. The clay-Rs correlation "
         "flips: r_Asia = +0.302, r_US = -0.048.",
         fontsize=10, va="top")

# ── Row 3: methodology evolution panel (full width) ──────────────────
ax_r3 = fig.add_subplot(gs[3, 0:8])
ax_r3.set_facecolor(C["paper"]); ax_r3.set_xlim(0, 1); ax_r3.set_ylim(0, 1); ax_r3.axis("off")
add_text(ax_r3, 0.0, 1.0,
         "06  ·  METHODOLOGY EVOLUTION  —  what each model adds, where each one fails",
         family=F["mono"], fontsize=11, color=C["accent"], weight="bold")
mep_path = OUT / "methodology_evolution_panel.png"
if mep_path.exists():
    ax_inset = ax_r3.inset_axes([0.0, 0.0, 1.0, 0.96])
    img = mpimg.imread(mep_path)
    ax_inset.imshow(img, aspect="auto")
    ax_inset.axis("off")

# Right column of bottom row — split into Köppen + Implications stacked
# Actually use the remaining 4-column block for sensor connection + impl
ax_r4_top = fig.add_subplot(gs[3, 8:12])
ax_r4_top.set_facecolor(C["paper"]); ax_r4_top.set_xlim(0, 1); ax_r4_top.set_ylim(0, 1); ax_r4_top.axis("off")

# Sensor connection figure top half
add_text(ax_r4_top, 0.0, 1.0,
         "07  ·  SENSOR CONNECTION  ·  what the satellite cannot resolve",
         family=F["mono"], fontsize=11, color=C["accent"], weight="bold")
sensor_path = OUT / "sensor_connection_figure.png"
if sensor_path.exists():
    ax_inset = ax_r4_top.inset_axes([0.0, 0.55, 1.0, 0.41])
    img = mpimg.imread(sensor_path)
    ax_inset.imshow(img, aspect="auto")
    ax_inset.axis("off")

# Köppen + roadmap text (bottom half of right column)
koppen_text = (
    "08  ·  KÖPPEN STRATIFICATION  ·  doesn't help\n"
    f"    Köppen C  R² = {kopC['transfer_r2']:+.3f}  CI ({kopC['ci_low']:+.2f}, {kopC['ci_high']:+.2f})  spans 0\n"
    f"    Köppen D  R² = {kopD['transfer_r2']:+.3f}  CI ({kopD['ci_low']:+.2f}, {kopD['ci_high']:+.2f})  significantly negative\n"
    f"    Cross-zone reference  R² = {F_['median']:+.3f}  CI ({F_['ci_low']:+.2f}, {F_['ci_high']:+.2f})\n"
    "\n"
    "    The cross-zone +0.127 IS the cross-zone precipitation gradient.\n"
    "    Stratifying it away leaves no transferable signal.\n"
    "\n"
    "09  ·  ROADMAP  ·  three deliverables, three months\n"
    "    1.  MODIS NPP integration                          ≤ 2 weeks\n"
    "    2.  ESSD manuscript submission                     ≤ 6 weeks\n"
    "    3.  Co-located biosensor pilot at SRDB site        ≤ 12 weeks\n"
    "\n"
    "REFERENCES\n"
    "    Bond-Lamberty 2010, 2020 · Fick & Hijmans 2017 · Hashimoto 2015\n"
    "    (10.5194/bg-12-4121-2015) · Jian 2021 (10.5194/essd-13-255-2021)\n"
    "    · Poggio 2021 · Stell 2021 (10.1111/gcb.15666)\n"
    "    · Warner 2019 (10.1029/2019GB006264) · Yao 2021\n"
    "    (10.1029/2020GB006918)."
)
add_text(ax_r4_top, 0.0, 0.51, koppen_text, fontsize=10,
         family=F["mono"], va="top", linespacing=1.45)

# Save PDF + raster preview
pdf_path = OUT / "genius_poster.pdf"
png_path = OUT / "genius_poster.png"
fig.savefig(pdf_path, facecolor=C["paper"])  # vector
fig.savefig(png_path, dpi=100, facecolor=C["paper"])  # 100 DPI = ~3600x2400 preview
plt.close(fig)
print(f"Wrote {pdf_path}")
print(f"Wrote {png_path}")
