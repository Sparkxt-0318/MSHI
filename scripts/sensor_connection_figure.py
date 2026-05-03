"""Round C-2 — sensor connection conceptual figure.

Three-panel horizontal layout in the Bedrock palette:
  [A] EAB schematic (biofilm on electrode, electrons through external circuit)
  [B] Mathematical link (current ∝ electron transfer ∝ substrate oxidation ∝ Rs)
  [C] Spatial × temporal coverage comparison (chamber, satellite, biosensor)

This is a CONCEPTUAL figure, not a real-data plot. Real EAB-vs-Rs data
co-located at SRDB sites does not exist yet — that pilot deployment is
on the roadmap (slide 11 of the pitch deck).

Outputs:
  data/outputs/sensor_connection_figure.png       (300 DPI print)
  data/outputs/sensor_connection_figure_screen.png (160 DPI deck)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle, Wedge
from matplotlib.lines import Line2D
import numpy as np

OUT = Path("/home/user/MSHI/data/outputs")

# Bedrock palette
C = {
    "paper":    "#FAF8F5",
    "ink":      "#0E1116",
    "ink_soft": "#3A4048",
    "rule":     "#C8CCD2",
    "accent":   "#A4221A",
    "ocean":    "#EEF2F4",
    "soil":     "#8B6F47",  # warm soil tone
    "biofilm":  "#5C8A3A",  # green for biofilm
    "metal":    "#7A828B",  # neutral grey for electrodes
}


def panel_A(ax):
    """EAB schematic: biofilm on anode, e- flow through external circuit to cathode."""
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("A.  Electrochemically Active Biofilm",
                 fontsize=12, fontweight="bold", color=C["ink"], pad=8, loc="left")

    # Soil layer (background)
    soil = Rectangle((0.5, 0.7), 9, 4.0, facecolor=C["soil"], alpha=0.18,
                     edgecolor="none", zorder=1)
    ax.add_patch(soil)
    ax.text(0.7, 4.4, "soil matrix", fontsize=8, color=C["ink_soft"],
            style="italic", zorder=2)

    # Anode rod (left)
    anode = Rectangle((2.4, 0.8), 0.4, 4.5, facecolor=C["metal"],
                      edgecolor=C["ink"], lw=0.6, zorder=3)
    ax.add_patch(anode)
    ax.text(2.6, 0.5, "anode", fontsize=8.5, color=C["ink"],
            ha="center", weight="bold", zorder=4)

    # Biofilm on anode
    for y in np.linspace(1.2, 5.0, 8):
        ax.add_patch(Wedge((2.8, y), 0.3, 270, 90,
                           facecolor=C["biofilm"], edgecolor="none",
                           alpha=0.85, zorder=5))
    ax.text(3.3, 5.3, "EAB biofilm", fontsize=8.5, color=C["biofilm"],
            weight="bold", zorder=6)

    # Cathode rod (right)
    cathode = Rectangle((7.2, 0.8), 0.4, 4.5, facecolor=C["metal"],
                        edgecolor=C["ink"], lw=0.6, zorder=3)
    ax.add_patch(cathode)
    ax.text(7.4, 0.5, "cathode", fontsize=8.5, color=C["ink"],
            ha="center", weight="bold", zorder=4)

    # External circuit (current arrow loop)
    # wire from anode top, up, across, down to cathode top
    ax.plot([2.6, 2.6], [5.3, 7.5], color=C["ink"], lw=1.4, zorder=2)
    ax.plot([2.6, 7.4], [7.5, 7.5], color=C["ink"], lw=1.4, zorder=2)
    ax.plot([7.4, 7.4], [7.5, 5.3], color=C["ink"], lw=1.4, zorder=2)

    # Current arrow (e- flow direction in external circuit: anode → cathode)
    ax.annotate("", xy=(7.4, 7.45), xytext=(2.6, 7.45),
                arrowprops=dict(arrowstyle="-|>", color=C["accent"], lw=1.6))
    ax.text(5.0, 8.1, "I  (current)", fontsize=11, color=C["accent"],
            ha="center", weight="bold")
    ax.text(5.0, 7.7, "electron transfer in external circuit",
            fontsize=8, color=C["ink_soft"], ha="center", style="italic")

    # Substrate label inside biofilm
    ax.annotate("", xy=(2.95, 3.2), xytext=(4.2, 3.7),
                arrowprops=dict(arrowstyle="->", color=C["ink_soft"],
                                lw=0.8))
    ax.text(4.3, 3.7, "substrate (organic C)\noxidised by biofilm",
            fontsize=8, color=C["ink_soft"], va="center")

    # e- arrows from biofilm to anode
    for y in [1.8, 3.0, 4.2]:
        ax.annotate("", xy=(2.8, y), xytext=(3.3, y),
                    arrowprops=dict(arrowstyle="->", color=C["accent"],
                                    lw=0.7, alpha=0.6))


def panel_B(ax):
    """Mathematical link: current ∝ electron transfer ∝ substrate ox ∝ Rs."""
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    ax.set_title("B.  The biological linkage",
                 fontsize=12, fontweight="bold", color=C["ink"], pad=8, loc="left")

    chain = [
        ("$I$", "current\n(measured)", C["accent"]),
        ("$r_e$", "electron transfer rate\n(stoichiometric)", C["ink"]),
        ("$r_{ox}$", "substrate oxidation rate\n(microbial metabolism)", C["ink"]),
        ("$R_s$", "soil respiration flux\n(annual carbon export)", C["accent"]),
    ]
    n = len(chain)
    y_centres = np.linspace(8.4, 1.2, n)
    for i, (sym, label, col) in enumerate(chain):
        # Symbol bubble
        circ = Circle((1.6, y_centres[i]), 0.7, facecolor=C["paper"],
                      edgecolor=col, lw=1.6, zorder=3)
        ax.add_patch(circ)
        ax.text(1.6, y_centres[i], sym, fontsize=18, color=col,
                ha="center", va="center", weight="bold", zorder=4)
        ax.text(2.7, y_centres[i], label, fontsize=10, color=C["ink"],
                va="center", ha="left")

        # Arrow to next
        if i < n - 1:
            ax.annotate("", xy=(1.6, y_centres[i+1] + 0.7),
                        xytext=(1.6, y_centres[i] - 0.7),
                        arrowprops=dict(arrowstyle="-|>", color=C["ink_soft"],
                                        lw=1.2))
            # ∝ symbol
            ax.text(2.0, (y_centres[i] + y_centres[i+1])/2, "∝",
                    fontsize=14, color=C["ink_soft"],
                    ha="left", va="center", style="italic")

    ax.text(0.4, -0.4,
            "Current measured at the EAB anode is proportional, by Faradaic\n"
            "stoichiometry, to the rate at which the microbial biofilm\n"
            "oxidises soil organic substrate — the same metabolism that the\n"
            "annual chamber Rs flux integrates over a year.",
            fontsize=8.5, color=C["ink_soft"], style="italic",
            ha="left", va="top", linespacing=1.4)


def panel_C(ax):
    """Spatial × temporal coverage comparison."""
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    ax.set_title("C.  Coverage comparison",
                 fontsize=12, fontweight="bold", color=C["ink"], pad=8, loc="left")

    # Three rows = three methods. Each row has spatial-density bar and
    # temporal-density bar drawn alongside.
    methods = [
        # (label, color, spatial_pct, temporal_pct, descriptor)
        ("Chamber + EC",  C["ink_soft"], 0.10, 0.30, "metre footprint, monthly"),
        ("Satellite (this work)",  C["ink_soft"], 0.95, 0.55, "5 km grid, 8-day MODIS"),
        ("EAB biosensor", C["accent"],  0.40, 0.95, "centimetre, continuous"),
    ]
    # Headers
    ax.text(0.4, 8.6, "instrument", fontsize=10, color=C["ink"], weight="bold")
    ax.text(3.1, 8.6, "spatial density", fontsize=10, color=C["ink"], weight="bold")
    ax.text(6.6, 8.6, "temporal density", fontsize=10, color=C["ink"], weight="bold")
    ax.plot([0.3, 9.7], [8.4, 8.4], color=C["rule"], lw=0.8)

    row_y = [7.3, 5.6, 3.9]
    for i, (label, col, sp, tp, desc) in enumerate(methods):
        y = row_y[i]
        # Method label
        ax.text(0.4, y + 0.25, label, fontsize=10.5, color=col, weight="bold")
        ax.text(0.4, y - 0.15, desc, fontsize=8, color=C["ink_soft"], style="italic")

        # Spatial bar
        bar_w_full = 2.8
        ax.add_patch(Rectangle((3.1, y - 0.1), bar_w_full, 0.4,
                               facecolor=C["rule"], edgecolor="none", alpha=0.4))
        ax.add_patch(Rectangle((3.1, y - 0.1), bar_w_full * sp, 0.4,
                               facecolor=col, edgecolor="none"))
        ax.text(3.1 + bar_w_full + 0.15, y + 0.1, f"{int(sp*100)}%",
                fontsize=9, color=col, weight="bold", va="center")

        # Temporal bar
        ax.add_patch(Rectangle((6.6, y - 0.1), bar_w_full, 0.4,
                               facecolor=C["rule"], edgecolor="none", alpha=0.4))
        ax.add_patch(Rectangle((6.6, y - 0.1), bar_w_full * tp, 0.4,
                               facecolor=col, edgecolor="none"))
        ax.text(6.6 + bar_w_full + 0.15, y + 0.1, f"{int(tp*100)}%",
                fontsize=9, color=col, weight="bold", va="center")

    ax.text(0.4, 2.4,
            "Chamber and satellite each fill one axis but not the other.\n"
            "The biosensor combination — high spatial density AND continuous\n"
            "temporal coverage at low cost — is the empty quadrant.",
            fontsize=8.5, color=C["ink"], style="italic", linespacing=1.4)
    ax.text(0.4, 0.7,
            "Coverage values are illustrative — first co-located\n"
            "EAB / chamber Rs deployment queued for next phase.",
            fontsize=7.5, color=C["ink_soft"], linespacing=1.3)


def main() -> int:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5),
                             gridspec_kw={"wspace": 0.05},
                             facecolor=C["paper"])
    panel_A(axes[0])
    panel_B(axes[1])
    panel_C(axes[2])
    fig.suptitle(
        "From electron transfer to soil respiration — closing the resolution gap",
        fontsize=14, fontweight="bold", color=C["ink"], y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT / "sensor_connection_figure.png", dpi=300,
                facecolor=C["paper"], bbox_inches="tight")
    fig.savefig(OUT / "sensor_connection_figure_screen.png", dpi=160,
                facecolor=C["paper"], bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {OUT / 'sensor_connection_figure.png'}")
    print(f"Wrote {OUT / 'sensor_connection_figure_screen.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
