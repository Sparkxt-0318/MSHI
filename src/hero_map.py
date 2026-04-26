"""
hero_map.py — render the MSHI-Geo hero visual for the Genius Olympiad poster.

What this produces:
    data/outputs/hero_mshi_geo_asia.png   — print/poster (300 DPI)
    data/outputs/hero_mshi_geo_asia.pdf   — vector for poster
    data/outputs/hero_mshi_geo_asia_screen.png  — slide deck (160 DPI)

Design principles (Bedrock-consistent):
    - Diverging RdBu_r colormap centered at 1.0 (composite = climate-corrected Rs)
        red    = soil respiration BELOW climate expectation (degraded)
        white  = at expectation
        blue   = ABOVE expectation (healthier than climate would predict)
    - Country borders as quiet scaffolding (Natural Earth, low-saturation gray)
    - Annotated degradation hotspots with small text labels
    - Single explicit legend with biological interpretation, not just numbers
    - Monospace metadata block (date, model R², N points) bottom-right
    - Generous whitespace, restrained typography, 1 accent color (deep red)

Inputs:
    composite parquet with columns: longitude, latitude, mshi_geo_anomaly
    (this is predicted_Rs / climate_expected_Rs)

Run:
    python src/hero_map.py --composite data/processed/asia_grid_5km_anomaly.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("mshi_geo.hero")

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "data" / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Bedrock-style design tokens
# ─────────────────────────────────────────────────────────────────────────────
BEDROCK = {
    # Colors
    "ink":        "#0E1116",   # near-black for text + borders
    "ink_soft":   "#3A4048",   # secondary text
    "rule":       "#C8CCD2",   # hairline rules and country borders
    "paper":      "#FFFFFF",
    "paper_warm": "#FAF8F5",   # subtle warm cream for figure background
    "ocean":      "#EEF2F4",   # ocean / no-data tone
    "accent":     "#A4221A",   # one strong accent (deep red — used sparingly)
    # Diverging colormap stops (red → white → blue)
    "div_red_dark":  "#7B0E0E",
    "div_red":       "#C8401C",
    "div_red_pale":  "#F4C2A8",
    "div_neutral":   "#F8F4EE",
    "div_blue_pale": "#B6D4E8",
    "div_blue":      "#3F7CAB",
    "div_blue_dark": "#1F4068",
}

# Degradation hotspots to annotate (lon, lat, label, label_anchor)
HOTSPOTS = [
    (115.0, 37.5, "North China Plain",     "right"),
    ( 78.0, 27.0, "Indo-Gangetic Plain",   "right"),
    ( 65.0, 45.0, "Central Asian Steppe",  "right"),
    (105.0, 35.0, "Loess Plateau",         "left"),
    ( 50.0, 33.0, "Iranian Plateau",       "left"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Country borders (lazy-loaded; falls back to no-borders if not available)
# ─────────────────────────────────────────────────────────────────────────────
def load_country_borders():
    """
    Try to load Natural Earth admin_0 country borders.
    Returns a GeoDataFrame or None if unavailable.
    """
    try:
        import geopandas as gpd
    except ImportError:
        LOG.warning("geopandas not installed — borders will be omitted")
        return None

    candidates = [
        ROOT / "data" / "raw" / "borders" / "ne_50m_admin_0_countries.shp",
        ROOT / "data" / "raw" / "borders" / "ne_110m_admin_0_countries.shp",
    ]
    for path in candidates:
        if path.exists():
            LOG.info("Loading country borders from %s", path)
            return gpd.read_file(path)

    # Try to fetch from Natural Earth if internet is available
    try:
        import urllib.request, zipfile, io
        ne_url = ("https://naturalearth.s3.amazonaws.com/"
                  "50m_cultural/ne_50m_admin_0_countries.zip")
        LOG.info("Country borders not found locally, fetching from Natural Earth...")
        out_dir = ROOT / "data" / "raw" / "borders"
        out_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(ne_url, timeout=30) as r:
            with zipfile.ZipFile(io.BytesIO(r.read())) as zf:
                zf.extractall(out_dir)
        return gpd.read_file(out_dir / "ne_50m_admin_0_countries.shp")
    except Exception as e:
        LOG.warning("Could not fetch country borders: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Diverging colormap construction
# ─────────────────────────────────────────────────────────────────────────────
def build_diverging_cmap():
    """Build the Bedrock diverging colormap."""
    from matplotlib.colors import LinearSegmentedColormap
    stops = [
        (0.00, BEDROCK["div_red_dark"]),
        (0.20, BEDROCK["div_red"]),
        (0.40, BEDROCK["div_red_pale"]),
        (0.50, BEDROCK["div_neutral"]),
        (0.60, BEDROCK["div_blue_pale"]),
        (0.80, BEDROCK["div_blue"]),
        (1.00, BEDROCK["div_blue_dark"]),
    ]
    return LinearSegmentedColormap.from_list("bedrock_div", stops, N=256)


# ─────────────────────────────────────────────────────────────────────────────
# Grid → 2D array
# ─────────────────────────────────────────────────────────────────────────────
def df_to_grid(df: pd.DataFrame, value_col: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reshape a (lon, lat, value) dataframe into a 2D grid."""
    lons = np.sort(df["longitude"].unique())
    lats = np.sort(df["latitude"].unique())
    grid = (
        df.set_index(["latitude", "longitude"])[value_col]
        .unstack("longitude")
        .reindex(index=lats, columns=lons)
        .to_numpy()
    )
    return lons, lats, grid


# ─────────────────────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────────────────────
def render_hero_map(
    df: pd.DataFrame,
    out_path_png: Path,
    out_path_pdf: Path,
    out_path_screen: Path,
    metadata: Optional[Dict] = None,
    value_col: str = "mshi_geo_anomaly",
    bbox: Tuple[float, float, float, float] = (25.0, -10.0, 180.0, 80.0),
    vmin: float = 0.5,
    vmax: float = 1.5,
):
    """
    Render the hero visual.

    Parameters
    ----------
    df : DataFrame with longitude, latitude, and the anomaly column
    metadata : dict with optional keys 'cv_r2', 'transfer_r2', 'n_train', 'n_us', 'date'
    bbox : (lon_min, lat_min, lon_max, lat_max) crop
    vmin/vmax : colormap bounds; defaults span the typical 0.5x-1.5x range
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib import patheffects as pe

    # Typography setup
    plt.rcParams.update({
        "font.family":      "sans-serif",
        "font.sans-serif":  ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "axes.edgecolor":   BEDROCK["ink"],
        "axes.linewidth":   0.8,
        "axes.labelcolor":  BEDROCK["ink_soft"],
        "xtick.color":      BEDROCK["ink_soft"],
        "ytick.color":      BEDROCK["ink_soft"],
        "xtick.major.size": 3, "ytick.major.size": 3,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    })

    cmap = build_diverging_cmap()

    # Data → grid
    lons, lats, grid = df_to_grid(df, value_col)
    lon_min, lat_min, lon_max, lat_max = bbox

    fig = plt.figure(figsize=(16, 10), facecolor=BEDROCK["paper_warm"])

    # Layout: title strip / map / metadata strip
    gs = fig.add_gridspec(
        nrows=3, ncols=2,
        height_ratios=[0.10, 0.85, 0.06],
        width_ratios=[0.78, 0.22],
        wspace=0.04, hspace=0.04,
        left=0.04, right=0.97, top=0.97, bottom=0.04,
    )

    # ── Title strip ─────────────────────────────────────────────────────────
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    ax_title.text(
        0.0, 0.78, "MSHI-GEO  /  ASIA",
        fontsize=11, fontweight="bold", color=BEDROCK["accent"],
        family="monospace", transform=ax_title.transAxes,
    )
    ax_title.text(
        0.0, 0.36,
        "Climate-Corrected Soil Microbial Respiration Anomaly",
        fontsize=22, fontweight="bold", color=BEDROCK["ink"],
        transform=ax_title.transAxes,
    )
    ax_title.text(
        0.0, 0.05,
        "Predicted soil respiration ÷ climate-expected soil respiration. "
        "Values below 1.0 indicate microbial activity is suppressed relative to "
        "what climate alone would support — a signal of soil-driven degradation.",
        fontsize=10, color=BEDROCK["ink_soft"],
        transform=ax_title.transAxes, style="italic",
    )
    # Hairline rule under title
    ax_title.axhline(y=-0.05, color=BEDROCK["rule"], linewidth=0.6, xmin=0.0, xmax=1.0)

    # ── Main map ────────────────────────────────────────────────────────────
    ax = fig.add_subplot(gs[1, 0])
    ax.set_facecolor(BEDROCK["ocean"])

    # Imshow the prediction grid
    im = ax.imshow(
        grid,
        extent=(lons.min(), lons.max(), lats.min(), lats.max()),
        origin="lower",
        cmap=cmap,
        norm=Normalize(vmin=vmin, vmax=vmax),
        interpolation="bilinear",
        aspect="auto",
        zorder=2,
    )

    # Country borders
    borders = load_country_borders()
    if borders is not None:
        try:
            borders.boundary.plot(
                ax=ax, color=BEDROCK["rule"], linewidth=0.45,
                alpha=0.85, zorder=3,
            )
        except Exception as e:
            LOG.warning("border plot failed: %s", e)

    # Hotspot annotations
    for lon, lat, label, side in HOTSPOTS:
        if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
            continue
        ax.plot(lon, lat, "o",
                markerfacecolor="white",
                markeredgecolor=BEDROCK["ink"],
                markeredgewidth=1.0,
                markersize=4.5, zorder=5)
        offset = (4, 4) if side == "right" else (-4, 4)
        ha = "left" if side == "right" else "right"
        txt = ax.annotate(
            label,
            xy=(lon, lat),
            xytext=(offset[0], offset[1]),
            textcoords="offset points",
            fontsize=8.5, color=BEDROCK["ink"],
            fontweight="600", ha=ha, va="bottom",
            zorder=6,
        )
        txt.set_path_effects([
            pe.withStroke(linewidth=2.4, foreground="white", alpha=0.85),
        ])

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude",  fontsize=9)
    ax.tick_params(labelsize=8)

    # Subtle frame
    for spine in ax.spines.values():
        spine.set_color(BEDROCK["ink"])
        spine.set_linewidth(0.7)

    # ── Legend / interpretation panel ───────────────────────────────────────
    ax_legend = fig.add_subplot(gs[1, 1])
    ax_legend.axis("off")

    # Colorbar across top of the panel (horizontal)
    cb_ax = ax_legend.inset_axes([0.08, 0.88, 0.84, 0.030])
    cb = fig.colorbar(im, cax=cb_ax, orientation="horizontal")
    cb.outline.set_linewidth(0.6)
    cb.outline.set_edgecolor(BEDROCK["ink"])
    cb.ax.tick_params(labelsize=7.0, color=BEDROCK["ink_soft"], pad=2)
    cb.set_ticks([vmin, 0.75, 1.0, 1.25, vmax])
    cb.set_ticklabels([f"{vmin:.2f}", "0.75", "1.00", "1.25", f"{vmax:.2f}"])
    ax_legend.text(
        0.08, 0.945, "ANOMALY RATIO",
        family="monospace", fontsize=7.5, fontweight="bold",
        color=BEDROCK["ink_soft"], transform=ax_legend.transAxes,
    )

    # Interpretation header
    ax_legend.text(
        0.08, 0.78, "INTERPRETATION",
        family="monospace", fontsize=8.5, fontweight="bold",
        color=BEDROCK["accent"], transform=ax_legend.transAxes,
    )

    # Interpretation rows — full panel width, swatch + bold value + description below
    rows = [
        (0.71, BEDROCK["div_blue_dark"], "≥ 1.25",
            "Microbial activity exceeds climate expectation"),
        (0.57, BEDROCK["div_blue_pale"], "1.00 – 1.25",
            "Healthy / functioning soils"),
        (0.43, BEDROCK["div_neutral"],   "≈ 1.00",
            "At climate expectation"),
        (0.29, BEDROCK["div_red_pale"],  "0.75 – 1.00",
            "Mild suppression"),
        (0.10, BEDROCK["div_red"],       "≤ 0.75",
            "Significant degradation —\naddressable by management"),
    ]
    for y, swatch, val, desc in rows:
        ax_legend.add_patch(plt.Rectangle(
            (0.08, y), 0.05, 0.045,
            facecolor=swatch, edgecolor=BEDROCK["ink"], linewidth=0.4,
            transform=ax_legend.transAxes,
        ))
        ax_legend.text(
            0.16, y + 0.022, val,
            fontsize=8.5, fontweight="bold", color=BEDROCK["ink"],
            transform=ax_legend.transAxes, va="center",
        )
        ax_legend.text(
            0.46, y + 0.022, desc,
            fontsize=7.8, color=BEDROCK["ink_soft"],
            transform=ax_legend.transAxes, va="center",
        )

    # ── Metadata strip ─────────────────────────────────────────────────────
    ax_meta = fig.add_subplot(gs[2, :])
    ax_meta.axis("off")
    ax_meta.axhline(y=0.95, color=BEDROCK["rule"], linewidth=0.6, xmin=0, xmax=1)

    md = metadata or {}
    today = md.get("date", date.today().isoformat())
    cv_r2 = md.get("cv_r2", "—")
    tr_r2 = md.get("transfer_r2", "—")
    n_train = md.get("n_train", "—")
    n_us = md.get("n_us", "—")
    res = md.get("resolution_km", "—")

    fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    left_strs = [
        f"MODEL  XGBoost  ·  spatial-block CV  ·  resolution {res} km",
        f"DATA   COSORE + SRDB soil respiration  ·  SoilGrids 2.0  ·  WorldClim 2.1  ·  MODIS",
    ]
    right_strs = [
        f"CV R²  {fmt(cv_r2)}    Asia→US R²  {fmt(tr_r2)}",
        f"N(train)={n_train}   N(US)={n_us}   {today}",
    ]
    for i, s in enumerate(left_strs):
        ax_meta.text(0.005, 0.55 - i * 0.40, s,
                     family="monospace", fontsize=7.5,
                     color=BEDROCK["ink_soft"], transform=ax_meta.transAxes)
    for i, s in enumerate(right_strs):
        ax_meta.text(0.995, 0.55 - i * 0.40, s,
                     family="monospace", fontsize=7.5, ha="right",
                     color=BEDROCK["ink_soft"], transform=ax_meta.transAxes)

    # ── Save ────────────────────────────────────────────────────────────────
    out_path_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path_png, dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    fig.savefig(out_path_pdf, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    fig.savefig(out_path_screen, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)

    LOG.info("Saved hero map:")
    LOG.info("  print  → %s", out_path_png)
    LOG.info("  vector → %s", out_path_pdf)
    LOG.info("  screen → %s", out_path_screen)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────
def main(composite_path: Path, value_col: str = "mshi_geo_anomaly") -> int:
    df = pd.read_parquet(composite_path)
    LOG.info("Loaded %d cells from %s", len(df), composite_path)

    if value_col not in df.columns:
        LOG.error("Column '%s' not in parquet. Columns: %s",
                  value_col, list(df.columns))
        return 1

    metrics_path = OUTPUTS / "training_metrics.json"
    val_path = OUTPUTS / "validation_report.json"
    metadata = {}
    if metrics_path.exists():
        m = json.loads(metrics_path.read_text())
        metadata["cv_r2"] = m.get("cv_mean_r2")
        metadata["n_train"] = m.get("n_train_total")
    if val_path.exists():
        v = json.loads(val_path.read_text())
        metadata["transfer_r2"] = v.get("asia_to_us_transfer", {}).get("r2")
        metadata["n_us"] = v.get("n_us_points")
    metadata["resolution_km"] = "~5"

    render_hero_map(
        df,
        OUTPUTS / "hero_mshi_geo_asia.png",
        OUTPUTS / "hero_mshi_geo_asia.pdf",
        OUTPUTS / "hero_mshi_geo_asia_screen.png",
        metadata=metadata,
        value_col=value_col,
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--composite", required=True,
                   help="Path to parquet with longitude, latitude, mshi_geo_anomaly")
    p.add_argument("--value-col", default="mshi_geo_anomaly")
    args = p.parse_args()
    raise SystemExit(main(Path(args.composite), args.value_col))
