"""One figure style for the whole paper (brief section 7): the Okabe-Ito colour-blind-safe palette, a single
font size scale, and ``save_figure``, which writes a 300-dpi PNG and a vector PDF and returns both paths
(stages record them as outputs). Figures carry no timestamps or metadata that would change between runs."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")                     # no display; deterministic rendering
import matplotlib.pyplot as plt  # noqa: E402

# Okabe & Ito (2008) colour-universal-design palette
PALETTE = {"black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
           "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#999999"}
CONTINENT_COLOURS = {"Asia": PALETTE["vermillion"], "Europe": PALETTE["blue"], "North America": PALETTE["orange"],
                     "South America": PALETTE["green"], "Africa": PALETTE["purple"], "Oceania": PALETTE["sky"]}
DPI = 300

plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42, "svg.hashsalt": "mshi",
                     "figure.dpi": 100})


def save_figure(fig, path_stem: str | Path) -> list[Path]:
    """Save ``fig`` as ``<stem>.png`` (300 dpi) and ``<stem>.pdf`` (vector) without volatile metadata."""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    png, pdf = stem.with_suffix(".png"), stem.with_suffix(".pdf")
    fig.savefig(png, dpi=DPI, bbox_inches="tight", metadata={"Software": None})
    fig.savefig(pdf, bbox_inches="tight", metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return [png, pdf]
