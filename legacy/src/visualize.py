"""
visualize.py — render poster-quality maps from MSHI-Geo predictions.

Outputs:
    data/outputs/asia_mshi_geo_map.png   — hero visual
    data/outputs/asia_mbc_pred_map.png   — predicted microbial biomass C
    data/outputs/asia_components_panel.png — 4-panel sub-score breakdown
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

LOG = logging.getLogger("mshi_geo.viz")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def render_map(
    df: pd.DataFrame,
    column: str,
    out_path: Path,
    title: str,
    cmap: str = "viridis",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    figsize=(13, 9),
):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    lons = np.sort(df["longitude"].unique())
    lats = np.sort(df["latitude"].unique())
    nx, ny = len(lons), len(lats)

    grid = (
        df.set_index(["latitude", "longitude"])[column]
        .unstack("longitude")
        .reindex(index=lats, columns=lons)
        .to_numpy()
    )

    if vmin is None:
        vmin = float(np.nanpercentile(grid, 2))
    if vmax is None:
        vmax = float(np.nanpercentile(grid, 98))

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(
        grid,
        extent=(lons.min(), lons.max(), lats.min(), lats.max()),
        origin="lower",
        cmap=cmap,
        norm=Normalize(vmin=vmin, vmax=vmax),
        interpolation="nearest",
        aspect="auto",
    )
    ax.set_title(title, fontsize=15)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(column, fontsize=11)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    LOG.info("Saved %s", out_path)


def render_component_panel(df: pd.DataFrame, out_path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cols = [
        ("c_mbc",   "Predicted MBC (normalized)",      "viridis"),
        ("c_soc",   "SOC stocks (normalized)",         "YlOrBr"),
        ("c_water", "Water habitability",              "Blues"),
        ("c_ph",    "pH optimality",                   "RdYlGn"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    lons = np.sort(df["longitude"].unique())
    lats = np.sort(df["latitude"].unique())

    for ax, (col, label, cmap) in zip(axes.ravel(), cols):
        grid = (
            df.set_index(["latitude", "longitude"])[col]
            .unstack("longitude")
            .reindex(index=lats, columns=lons)
            .to_numpy()
        )
        im = ax.imshow(
            grid,
            extent=(lons.min(), lons.max(), lats.min(), lats.max()),
            origin="lower", cmap=cmap, vmin=0, vmax=1, aspect="auto",
        )
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)

    fig.suptitle("MSHI-Geo Component Sub-Scores", fontsize=15, y=0.995)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    LOG.info("Saved %s", out_path)


def main(cfg_path: Path, composite_path: Path) -> int:
    cfg = yaml.safe_load(cfg_path.read_text())
    root = cfg_path.resolve().parents[1]
    df = pd.read_parquet(composite_path)
    LOG.info("Loaded composite predictions: %d rows", len(df))

    out_dir = root / "data" / "outputs"

    render_map(
        df, "mshi_geo",
        out_dir / "asia_mshi_geo_map.png",
        "MSHI-Geo: Continental Microbial Soil Health Index for Asia",
        cmap="viridis", vmin=0, vmax=1,
    )
    render_map(
        df, "mbc_pred",
        out_dir / "asia_mbc_pred_map.png",
        "Predicted Soil Microbial Biomass Carbon (mg C/kg soil)",
        cmap="viridis",
    )
    render_component_panel(df, out_dir / "asia_components_panel.png")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/mshi_geo.yaml")
    p.add_argument("--composite", required=True,
                   help="Path to *_with_composite.parquet from composite.py")
    args = p.parse_args()
    raise SystemExit(main(Path(args.config), Path(args.composite)))
