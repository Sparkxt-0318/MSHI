"""30_figures.py - one figure per analysis, consistent styling, colour-blind-safe palette.

Palette: categorical slots 1-3 of the dataviz reference palette (blue #2a78d6, orange #eb6834,
aqua #1baf7a; validated all-pairs on white: worst CVD dE 9.2, normal-vision dE 24.0); the same three
colours always mean Asia / North America / Europe (training continents). R2 heat maps use a
diverging blue (skill) - grey (0) - red (worse than the mean) ramp with matched OKLab lightness per
arm, saturating at +-0.5 (cell text gives the actual value). Grey = de-emphasis.

  fig1_a1_transfer_<v>      transfer matrix heat maps (XGBoost; OLS on log precipitation) with site
                            counts and 95% intervals; skill vs climate coverage of the test continent
  fig2_a2_ceiling_<v>       variance ceiling vs observed skill per continent; within-cell variance
                            components with 95% intervals; semivariograms
  fig3_a3_flagged_map       map of flagged SRDB records with proposed fixes; effect of flagged
                            records on transfer R2 (as-is / excluded / corrected)
Usage: python -I audit/30_figures.py
Outputs: audit/figures/*.png (300 dpi) and *.pdf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

FIG = C.ROOT / "audit" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
INK, INK2, MUTED, GRID, BASE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CONT_COL = {"Asia": BLUE, "North America": ORANGE, "Europe": AQUA}
CONT_MARK = {"Asia": "o", "North America": "^", "Europe": "s"}
ABBR = C.CONT_ABBR
DIV = LinearSegmentedColormap.from_list(
    "r2div", [(0.0, "#7a1c1c"), (0.2, "#c73a39"), (0.4, "#f4b3a6"), (0.5, "#f0efec"),
              (0.6, "#b7d3f6"), (0.8, "#2a78d6"), (1.0, "#104281")])
NORM = TwoSlopeNorm(vmin=-0.5, vcenter=0.0, vmax=0.5)
LABEL_REPORT = 200  # place_labels reports labels at or above this penalty


def text_on(rgba):
    r, g, b = rgba[:3]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "white" if lum < 0.45 else INK


def save(fig, name):
    for ext in ("png", "pdf"):
        meta = {"CreationDate": None} if ext == "pdf" else {}  # no timestamp: re-renders are byte-identical
        fig.savefig(FIG / f"{name}.{ext}", dpi=300, bbox_inches="tight", facecolor="white", metadata=meta)
    plt.close(fig)
    print("wrote", FIG / f"{name}.png")


def _dist_box(p, bb):
    """Distance (display units) from point p to bounding box bb (0 if inside)."""
    dx = max(bb.x0 - p[0], 0.0, p[0] - bb.x1)
    dy = max(bb.y0 - p[1], 0.0, p[1] - bb.y1)
    return float(np.hypot(dx, dy))


def _seg_hits_box(p, q, bb, n=40):
    return any(bb.x0 <= p[0] + t * (q[0] - p[0]) <= bb.x1 and bb.y0 <= p[1] + t * (q[1] - p[1]) <= bb.y1
               for t in np.linspace(0.0, 1.0, n))


def _exit_point(bb, p):
    """Point where the line from the centre of bb towards p leaves bb (start of a leader line)."""
    cx, cy = 0.5 * (bb.x0 + bb.x1), 0.5 * (bb.y0 + bb.y1)
    dx, dy = p[0] - cx, p[1] - cy
    t = 1.0
    if dx:
        t = min(t, ((bb.x1 if dx > 0 else bb.x0) - cx) / dx)
    if dy:
        t = min(t, ((bb.y1 if dy > 0 else bb.y0) - cy) / dy)
    return (cx + t * dx, cy + t * dy)


def _segs_cross(a, b, c, d):
    def orient(p, q, r):
        return np.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))
    return orient(a, b, c) != orient(a, b, d) and orient(c, d, a) != orient(c, d, b)


def _spread(want, h):
    """Positions as close as possible (least squares) to `want` (sorted high to low) while
    keeping consecutive positions at least h apart: isotonic regression by pool-adjacent-violators
    on want_i + i*h."""
    blocks = []  # [sum, count]
    for i, w in enumerate(want):
        blocks.append([w + i * h, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] < blocks[-1][0] / blocks[-1][1]:
            s_, c_ = blocks.pop()
            blocks[-1][0] += s_
            blocks[-1][1] += c_
    r = [b[0] / b[1] for b in blocks for _ in range(b[1])]
    return [ri - i * h for i, ri in enumerate(r)]


def place_labels(ax, pts, column_from=None, fontsize=5, color=INK2):
    """Label points without overlaps.

    pts: list of (x, y, lo, hi, text).
    1. Points with x >= column_from get their labels in a column to the right of the rightmost
       of them, ordered by y and spaced least-squares (_spread), each joined to its point by a
       leader line; ordered labels keep the lines from crossing.
    2. Every other label is placed greedily, crowded points first (higher first among equals),
       at its lowest-penalty candidate: 8 positions next to the point; positions 7 pt right or
       left shifted up or down in 3 pt steps; positions 12-48 pt away every 30 degrees (all but
       the first 8 with a leader line). Penalties:
         1000 per overlap with a marker or a placed label, and for leaving the axes;
          300 per leader line crossing another leader line, label or marker;
          200 per earlier leader line running through the label;
           60 if ambiguous (a label next to its point must be nearer to it than to any other
              marker by 1.5 pt; a label with a leader line must keep 5 pt from other markers);
           20 per error bar under the label (labels carry a white halo);
           25 + 1.5 x distance (pt) for a leader line.
       Labels at or above LABEL_REPORT are reported.
    Geometry is in points, so it does not depend on dpi.
    """
    fig = ax.figure
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    k = fig.dpi / 72.0
    axbox = ax.get_window_extent(rend)
    tr = ax.transData
    y0, y1 = ax.get_ylim()
    pix = [tuple(tr.transform((x, y))) for x, y, *_ in pts]
    markers = [Bbox.from_extents(px - 3.2 * k, py - 3.2 * k, px + 3.2 * k, py + 3.2 * k) for px, py in pix]
    bars = [Bbox.from_extents(px - 0.8 * k, tr.transform((x, max(lo, y0)))[1], px + 0.8 * k,
                              tr.transform((x, min(hi, y1)))[1])
            for (px, _), (x, _, lo, hi, _) in zip(pix, pts)]
    halo = [pe.withStroke(linewidth=1.8, foreground="white")]
    line = dict(arrowstyle="-", color=MUTED, linewidth=0.4, shrinkA=0.5, shrinkB=2.8)
    placed, segments = [], []  # label boxes and leader lines (start, end) in display units
    inside_y = [i for i in range(len(pts)) if y0 <= pts[i][1] <= y1]
    for i in set(range(len(pts))) - set(inside_y):
        print(f"  label '{pts[i][4]}' skipped: point outside the y range")

    # 1. callout column
    col = [i for i in inside_y if column_from is not None and pts[i][0] >= column_from]
    if col:
        order = sorted(col, key=lambda j: -pix[j][1])
        t = ax.text(0, 0, "Xg", fontsize=fontsize)
        h = t.get_window_extent(rend).height + 1.5 * k
        t.remove()
        pos = np.array(_spread([pix[j][1] for j in order], h))
        pos -= max(0.0, pos[0] - (axbox.y1 - h / 2))
        pos += max(0.0, (axbox.y0 + h / 2) - pos[-1])
        xcol = max(pix[j][0] for j in col) + 7 * k
        for j, py_lab in zip(order, pos):
            x, y, _, _, text = pts[j]
            ann = ax.annotate(text, (x, y), xytext=((xcol - pix[j][0]) / k, (py_lab - pix[j][1]) / k),
                              textcoords="offset points", ha="left", va="center", fontsize=fontsize,
                              color=color, zorder=4, path_effects=halo, arrowprops=dict(line, relpos=(0.0, 0.5)))
            ann.update_positions(rend)  # place the text first, then measure it without its leader line
            bb = Text.get_window_extent(ann, rend).padded(0.8 * k)
            placed.append(bb)
            segments.append(((bb.x0, 0.5 * (bb.y0 + bb.y1)), pix[j]))

    # 2. greedy placement of the rest
    def align(dx, dy):
        ha = "left" if dx > 1 else ("right" if dx < -1 else "center")
        va = "bottom" if dy > 1 else ("top" if dy < -1 else "center")
        return ha, va

    cands = ([(dx, dy, *align(dx, dy), False)
              for dx, dy in [(5, 0), (-5, 0), (0, 6), (0, -6), (4, 5), (4, -5), (-4, 5), (-4, -5)]]
             + [(sd * 7, dy, "left" if sd > 0 else "right", "center", True)
                for sd in (1, -1) for dy in range(-36, 37, 3) if abs(dy) > 4]
             + [(dx, dy, *align(dx, dy), True)
                for dx, dy in [(r * np.cos(a), r * np.sin(a)) for r in (12, 18, 26, 34, 42, 48)
                               for a in np.deg2rad(np.arange(0, 360, 30))]])

    def penalty(i, bb, dist_pt):
        if not (axbox.x0 <= bb.x0 and bb.x1 <= axbox.x1 and axbox.y0 <= bb.y0 and bb.y1 <= axbox.y1):
            return 1e6
        pen = 1000.0 * sum(bb.overlaps(o) for o in placed + markers)
        pen += 200.0 * sum(_seg_hits_box(a, b, bb) for a, b in segments)
        pen += 20.0 * sum(bb.overlaps(b) for b in bars)
        others = [_dist_box(pix[j], bb) for j in range(len(pix)) if j != i]
        if dist_pt is None:
            if others and _dist_box(pix[i], bb) >= min(others) - 1.5 * k:
                pen += 60.0
            return pen
        pen += 25.0 + 1.5 * dist_pt
        if others and min(others) < 5 * k:
            pen += 60.0
        start = _exit_point(bb, pix[i])
        pen += 300.0 * sum(_seg_hits_box(start, pix[i], m) for j, m in enumerate(markers) if j != i)
        pen += 300.0 * sum(_seg_hits_box(start, pix[i], o) for o in placed)
        pen += 300.0 * sum(_segs_cross(start, pix[i], a, b) for a, b in segments)
        return pen

    rest = [i for i in inside_y if i not in col]
    crowd = {i: sum(abs(pix[i][0] - q[0]) < 30 * k and abs(pix[i][1] - q[1]) < 30 * k for q in pix) for i in rest}
    for i in sorted(rest, key=lambda j: (-crowd[j], -pts[j][1])):
        x, y, _, _, text = pts[i]
        best = None
        for dx, dy, ha, va, is_far in cands:
            # measure the text alone (an annotation's extent would include its leader line)
            t = ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                            fontsize=fontsize, color=color, zorder=4, path_effects=halo)
            bb = t.get_window_extent(rend).padded(0.8 * k)
            t.remove()
            pen = penalty(i, bb, float(np.hypot(dx, dy)) if is_far else None)
            if best is None or pen < best[0]:
                best = (pen, dx, dy, ha, va, bb, is_far)
        pen, dx, dy, ha, va, bb, is_far = best
        ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=fontsize,
                    color=color, zorder=4, path_effects=halo, **({"arrowprops": line} if is_far else {}))
        if is_far:
            segments.append((_exit_point(bb, pix[i]), pix[i]))
        placed.append(bb)
        if pen >= LABEL_REPORT:
            print(f"  label '{text}' at ({x:.2f}, {y:.2f}) placed with penalty {pen:.0f}")


def heat(ax, res, model, title, counts, show_cbar=False):
    rows = ["Asia", "North America", "Europe"]
    cols = C.CONTINENT_ORDER
    M = np.full((len(rows), len(cols)), np.nan)
    for i, T in enumerate(rows):
        for j, E in enumerate(cols):
            kind = "within_blockcv" if T == E else "transfer"
            r = res[(res["kind"] == kind) & (res["train"] == T) & (res["test"] == E) & (res["model"] == model)]
            if len(r):
                r = r.iloc[0]
                M[i, j] = r["r2"]
                col = DIV(NORM(np.clip(r["r2"], -0.5, 0.5)))
                ax.add_patch(Rectangle((j, i), 1, 1, facecolor=col, edgecolor="white", linewidth=1.5))
                tc = text_on(col)
                ax.text(j + 0.5, i + 0.40, f"{r['r2']:+.2f}", ha="center", va="center", fontsize=7.5,
                        color=tc, fontweight="bold")
                ax.text(j + 0.5, i + 0.74, f"[{r['r2_lo']:+.2f}, {r['r2_hi']:+.2f}]", ha="center",
                        va="center", fontsize=5.6, color=tc)
                if T == E:
                    ax.add_patch(Rectangle((j + 0.04, i + 0.04), 0.92, 0.92, fill=False, edgecolor=INK,
                                           linewidth=0.9))
                    ax.text(j + 0.93, i + 0.13, "CV", ha="right", va="center", fontsize=4.8, color=tc)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(rows), 0)
    ax.set_xticks(np.arange(len(cols)) + 0.5)
    ax.set_xticklabels([f"{ABBR[c]}\nn={counts.get(c, 0)}" for c in cols], fontsize=6.5)
    ax.set_yticks(np.arange(len(rows)) + 0.5)
    ax.set_yticklabels([f"{ABBR[r]} (n={counts.get(r, 0)})" for r in rows], fontsize=6.5)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("Test continent (sites)", fontsize=7, color=INK2)
    ax.set_ylabel("Training continent (sites)", fontsize=7, color=INK2)
    ax.set_title(title, loc="left", fontsize=8)
    return M


def fig1(v):
    res = pd.read_csv(C.OUT / "a1" / f"transfer_{v}.csv")
    cov = pd.read_csv(C.OUT / "a1" / f"coverage_{v}.csv")
    counts = json.loads((C.OUT / "a1" / f"run_{v}.json").read_text())["counts"]
    fig = plt.figure(figsize=(7.2, 9.4))
    gs = fig.add_gridspec(3, 2, height_ratios=[0.78, 0.78, 1.25], hspace=0.55, wspace=0.3)
    ax1, ax2 = fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, :])
    heat(ax1, res, "xgb", "a  XGBoost on 8 bioclim variables (mean of 20 seeds; hyperparameters by spatial-block CV in the training continent)", counts)
    heat(ax2, res, "ols_P", "b  OLS on log annual precipitation", counts)
    top, bot = ax1.get_position().y1, ax2.get_position().y0  # colour bar spans panels a-b
    cax = fig.add_axes([0.93, bot + 0.1 * (top - bot), 0.012, 0.8 * (top - bot)])
    sm = plt.cm.ScalarMappable(norm=NORM, cmap=DIV)
    cb = fig.colorbar(sm, cax=cax, extend="both")
    cb.set_label("R$^2$ (log Rs); colour saturates at $\\pm$0.5", fontsize=6.5)
    cb.ax.tick_params(labelsize=6)
    cb.outline.set_linewidth(0.4)
    for k, (col, xlab, ax_pos, model) in enumerate([
            ("share_in_aoa_weighted", "Share of test sites inside the training continent's\narea of applicability (DI, Meyer & Pebesma 2021)", gs[2, 0], "xgb"),
            ("share_TP_in_range", "Share of test sites inside the training range\nof MAT and annual precipitation", gs[2, 1], "ols_P")]):
        ax = fig.add_subplot(ax_pos)
        ax.axhline(0, color=BASE, linewidth=0.6, zorder=0)
        pts = []
        for _, r in cov.sort_values(col).iterrows():
            y, lo, hi = r[f"r2_{model}"], r[f"r2_{model}_lo"], r[f"r2_{model}_hi"]
            ax.errorbar(r[col], y, yerr=[[y - lo], [hi - y]], fmt=CONT_MARK[r["train"]], color=CONT_COL[r["train"]],
                        markersize=5, markeredgecolor="white", markeredgewidth=0.6, elinewidth=0.6, capsize=0,
                        zorder=3)
            # marker colour/shape = training continent, so the label only names the test continent
            pts.append((r[col], y, lo, hi, f"$\\rightarrow${ABBR[r['test']]}"))
        ax.set_ylim(-1.2, 0.75)
        ax.set_xlim(-0.11, 1.2)  # room for labels beside points at 0 and 1; shares lie in [0, 1]
        ax.set_xticks(np.arange(0, 1.01, 0.2))
        ax.set_xlabel(xlab, fontsize=6.5)
        ax.set_ylabel("Transfer R$^2$ (95% interval)", fontsize=6.5)
        ax.grid(axis="y", color=GRID, linewidth=0.4)
        ttl = "c  XGBoost skill vs climate coverage" if model == "xgb" else "d  OLS (log P) skill vs range coverage"
        ax.set_title(ttl, loc="left", fontsize=8)
        place_labels(ax, pts, column_from=0.88)
    # one legend for c-d, below the panels, so it never covers data
    hs = [Line2D([], [], marker=CONT_MARK[c], color=CONT_COL[c], linestyle="", markersize=5,
                 markeredgecolor="white", label=f"trained on {c}") for c in CONT_COL]
    hs.append(Line2D([], [], linestyle="", label="label: $\\rightarrow$test continent"))
    fig.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.5, 0.042), ncol=4, frameon=False, fontsize=6,
               handletextpad=0.3, columnspacing=1.6)
    fig.text(0.01, 0.005, f"Variant: {v}. Diagonal = within-continent 5° spatial-block CV (outlined). Bracketed: "
             "95% bootstrap interval over test sites (2000 resamples). Descriptive only; no tests fitted to c-d.",
             fontsize=5.5, color=MUTED)
    save(fig, f"fig1_a1_transfer_{v}")


def fig2(v):
    a2 = json.loads((C.OUT / "a2" / "a2_results.json").read_text())["variants"][v]
    bt = pd.DataFrame(a2["bounds"])
    res = pd.read_csv(C.OUT / "a1" / f"transfer_{v}.csv")
    pc = pd.read_csv(C.OUT / "a2" / f"pair_components_{v}.csv").set_index("component")
    me = pd.read_csv(C.OUT / "a2" / f"method_ecosystem_{v}.csv")
    sv = pd.read_csv(C.OUT / "a2" / f"semivariogram_{v}.csv")
    fig = plt.figure(figsize=(7.2, 6.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1.0], height_ratios=[1.0, 0.85], hspace=0.78, wspace=0.42)
    # ---- a: ceiling vs observed ----
    ax = fig.add_subplot(gs[0, :])
    conts = C.CONTINENT_ORDER
    prim = bt[bt["estimator"] == "B2 nested study effects (primary)"].set_index("scope")
    b3 = bt[bt["estimator"].str.startswith("B3")].set_index("scope")
    XMIN = -0.6
    for i, c in enumerate(conts):
        if c not in prim.index:
            continue
        b, lo, hi = prim.loc[c, "r2max_sites"], prim.loc[c, "lo"], prim.loc[c, "hi"]
        ax.barh(i, b, left=0, height=0.55, color="#cde2fb", edgecolor="none", zorder=1)
        ax.barh(i, 1 - b, left=b, height=0.55, color="#ecebe6", edgecolor="none", zorder=1)
        ax.plot([lo, hi], [i, i], color=BLUE, linewidth=1.2, zorder=2, solid_capstyle="butt")
        ax.plot([b, b], [i - 0.27, i + 0.27], color=BLUE, linewidth=1.4, zorder=2)
        if c in b3.index:
            ax.plot(b3.loc[c, "r2max_sites"], i - 0.36, marker="v", color=INK2, markersize=4, zorder=4,
                    linestyle="")
        w = res[(res["kind"] == "within_blockcv") & (res["test"] == c) & (res["model"] == "xgb")]
        if len(w):
            x = w.iloc[0]["r2"]
            ax.plot(max(x, XMIN), i, marker="D", color=INK, markersize=4.5, zorder=5, linestyle="",
                    markeredgecolor="white", markeredgewidth=0.5)
        for T in ["Asia", "North America", "Europe"]:
            t = res[(res["kind"] == "transfer") & (res["train"] == T) & (res["test"] == c) & (res["model"] == "xgb")]
            if len(t):
                x = t.iloc[0]["r2"]
                off = {"Asia": -0.13, "North America": 0.0, "Europe": 0.13}[T]
                ax.plot(max(x, XMIN + 0.01), i + off, marker=CONT_MARK[T] if x >= XMIN else "<",
                        color=CONT_COL[T], markersize=4.5, zorder=4, linestyle="", markeredgecolor="white",
                        markeredgewidth=0.5)
    ax.axvline(0, color=BASE, linewidth=0.6, zorder=0)
    ax.set_xlim(XMIN, 1.0)
    ax.set_yticks(range(len(conts)))
    ax.set_yticklabels([f"{c} (n={int(prim.loc[c, 'n_sites'])})" for c in conts], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xlabel("Share of site-level variance of log Rs (R$^2$)", fontsize=7)
    ax.set_title("a  Ceiling on explainable variance for predictors constant within a 0.05° cell, and observed skill",
                 loc="left", fontsize=8)
    hs = [Patch(color="#cde2fb", label="explainable at 0.05° (ceiling B2, line = 95% interval)"),
          Patch(color="#ecebe6", label="not explainable: between-study + within-study scatter"),
          Line2D([], [], marker="v", color=INK2, linestyle="", markersize=4, label="B3: 1 - semivariance(0-10 km)/variance"),
          Line2D([], [], marker="D", color=INK, linestyle="", markersize=4, label="XGBoost, within-continent block CV")]
    hs += [Line2D([], [], marker=CONT_MARK[T], color=CONT_COL[T], linestyle="", markersize=4,
                  label=f"XGBoost transfer from {T}") for T in CONT_COL]
    ax.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.45, -0.17), fontsize=5.6, frameon=False, ncol=3)
    ax.grid(axis="x", color=GRID, linewidth=0.4)
    # ---- b: components ----
    ax = fig.add_subplot(gs[1, 0])
    items = [("Record pairs in the same cell", None, None, None),
             ("same study, same year", *pc.loc["same_study_same_year", ["half_sq_diff_cellw", "lo", "hi"]]),
             ("same study, different years", *pc.loc["same_study_diff_year", ["half_sq_diff_cellw", "lo", "hi"]]),
             ("different studies, same year", *pc.loc["diff_study_same_year", ["half_sq_diff_cellw", "lo", "hi"]]),
             ("different studies, different years", *pc.loc["diff_study_diff_year", ["half_sq_diff_cellw", "lo", "hi"]]),
             ("Measurement method", None, None, None)]
    for lab in ["IRGA-IRGA", "alkali/soda lime-alkali/soda lime", "GC-GC", "IRGA-alkali/soda lime", "IRGA-GC"]:
        r = me[(me["group"] == "method") & (me["label"] == lab)].iloc[0]
        items.append((lab.replace("alkali/soda lime-alkali/soda lime", "alkali/soda lime pairs") + f" ({int(r['n_cells'])} cells)",
                      r["half_sq_diff_cellw"], r["lo"], r["hi"]))
    items.append(("Ecosystem type", None, None, None))
    for lab in ["Forest", "Grassland", "Agriculture", "Wetland", "mixed ecosystem types"]:
        r = me[(me["group"] == "ecosystem") & (me["label"] == lab)].iloc[0]
        items.append((f"{lab} ({int(r['n_cells'])} cells)", r["half_sq_diff_cellw"], r["lo"], r["hi"]))
    for i, (lab, x, lo, hi) in enumerate(items):
        if x is None:
            ax.text(-0.02, i, lab, fontsize=6, fontweight="bold", color=INK, ha="right", va="center",
                    transform=ax.get_yaxis_transform())
            continue
        ax.plot([lo, hi], [i, i], color=INK2, linewidth=0.9)
        ax.plot(x, i, "o", color=INK, markersize=3.5)
    var_sites = float(prim.loc["All", "var_sites"])
    ax.axvline(var_sites, color=BLUE, linewidth=0.8)
    ax.text(var_sites + 0.008, len(items) - 1.2, f"variance of\nsite means\n{var_sites:.2f}", fontsize=5.3,
            color=BLUE, ha="left", va="bottom")
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([("" if x is None else "  " + lab) for lab, x, _, _ in items], fontsize=5.6)
    ax.set_ylim(len(items) - 0.5, -0.6)
    ax.set_xlim(0, 0.62)
    ax.set_xlabel("Half mean squared difference of log Rs (95% interval, cells resampled)", fontsize=6.3)
    ax.set_title("b  Within-cell disagreement by pair type", loc="left", fontsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.4)
    # ---- c: semivariograms ----
    ax = fig.add_subplot(gs[1, 1])
    for c in ["Asia", "North America", "Europe"]:
        s = sv[(sv["continent"] == c) & (sv["n_pairs"] > 0)]
        ax.plot(s["mean_lag_km"], s["gamma"], color=CONT_COL[c], linewidth=1.0, marker=CONT_MARK[c],
                markersize=3.5, markeredgecolor="white", markeredgewidth=0.5, label=c)
        var = a2["semivariogram"][c]["variance"]
        ax.axhline(var, color=CONT_COL[c], linewidth=0.5, alpha=0.6)
    ax.set_xscale("log")
    ax.set_ylim(0, 0.5)
    ax.set_xlabel("Distance between sites (km, bin mean)", fontsize=6.5)
    ax.set_ylabel("Semivariance of log Rs", fontsize=6.5)
    ax.set_title("c  Semivariograms (lines = site variance)", loc="left", fontsize=8)
    ax.legend(fontsize=6, frameon=False, loc="lower right")
    ax.grid(color=GRID, linewidth=0.4)
    fig.text(0.01, 0.005, f"Variant: {v}. Ceiling B2: nested study effects, site noise = s2_study x sum(n_ij/n_i)^2 + "
             "s2_rec/n_i. Transfer R2 below -0.6 drawn as '<' at the axis edge.", fontsize=5.5, color=MUTED)
    save(fig, f"fig2_a2_ceiling_{v}")


def fig3():
    import geopandas as gpd
    fl = pd.read_csv(C.OUT / "a3" / "flagged_records.csv")
    land = gpd.read_file(C.RAW / "naturalearth" / "ne_10m_land.geojson")
    land["geometry"] = land.geometry.simplify(0.15)
    G1, G2 = "sign error, lat/lon swap or same-site conflict (fix proposed)", "country label wrong"
    G3, G4 = "coordinates wrong, no fix (far offshore, unclear)", "near border or < 50 km offshore (low severity)"
    grp = {"lon_sign": G1, "lat_sign": G1, "both_signs": G1, "swap": G1, "swap_signs": G1, "same_site_conflict": G1,
           "label_wrong": G2,
           "coords_wrong": G3, "in_sea": G3, "unclear": G3, "near_border": G4, "offshore_near": G4}
    gcol = {G1: BLUE, G2: ORANGE, G3: AQUA, G4: MUTED}
    fl["group"] = fl["mismatch_class"].map(grp)
    loc = fl.groupby(["Latitude", "Longitude", "group", "confidence"]).agg(
        n=("Record_number", "size"), fix_lat=("fix_lat", "first"), fix_lon=("fix_lon", "first"),
        cls=("mismatch_class", "first")).reset_index()
    fig = plt.figure(figsize=(7.2, 7.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.45, 1.0], hspace=0.42)
    ax = fig.add_subplot(gs[0])
    land.plot(ax=ax, color="#ecebe6", edgecolor="#d6d5cf", linewidth=0.2)
    for (x0, y0, x1, y1), lab in [((25, -10, 180, 80), "original 'Asia' box"), ((-125, 24, -66, 50), "original 'US' box")]:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=INK2, linewidth=0.5, zorder=1))
        ax.text(x0 + 1, y1 + 1.5, lab, fontsize=5, color=INK2, va="bottom")
    sw = loc[loc["fix_lat"].notna() & loc["cls"].isin(["lon_sign", "lat_sign", "swap", "both_signs", "swap_signs",
                                                        "same_site_conflict"])]
    for _, r in sw.iterrows():
        ax.annotate("", xy=(r["fix_lon"], r["fix_lat"]), xytext=(r["Longitude"], r["Latitude"]),
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=0.5, alpha=0.7, mutation_scale=5), zorder=2)
    for g in [G4, G3, G2, G1]:
        s = loc[loc["group"] == g]
        for conf, filled in [("high", True), ("medium", False), ("low", False)]:
            t = s[s["confidence"] == conf]
            if t.empty:
                continue
            ax.scatter(t["Longitude"], t["Latitude"], s=8 + 3 * np.sqrt(t["n"]), marker="o",
                       facecolor=gcol[g] if filled else "white", edgecolor=gcol[g], linewidth=0.8,
                       zorder=2 if g == G4 else 3)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-62, 86)
    ax.set_xticks(range(-180, 181, 60))
    ax.set_yticks(range(-60, 81, 30))
    ax.tick_params(labelsize=6)
    ax.set_aspect("equal")
    counts = fl["group"].value_counts()
    hs = [Line2D([], [], marker="o", linestyle="", color=gcol[g], markerfacecolor=gcol[g], markersize=5,
                 label=f"{g} ({counts.get(g, 0)} records)") for g in [G1, G2, G3, G4]]
    hs += [Line2D([], [], marker="o", linestyle="", color=INK2, markerfacecolor=INK2, markersize=5, label="filled = high confidence"),
           Line2D([], [], marker="o", linestyle="", color=INK2, markerfacecolor="white", markersize=5, label="open = medium or low confidence"),
           Line2D([], [], color=BLUE, lw=0.8, label="arrow: original -> proposed coordinates")]
    ax.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.5, -0.07), fontsize=5.6, frameon=False, ncol=2)
    nchk = json.loads((C.OUT / 'a3' / 'box_contamination.json').read_text())['n_checked']
    ax.set_title(f"a  SRDB records whose Country field disagrees with their coordinates: {len(fl)} of {nchk} "
                 f"({fl['Study_number'].nunique()} studies)", loc="left", fontsize=8)
    # ---- b: effect ----
    ax = fig.add_subplot(gs[1])
    eff = C.OUT / "a3" / "effect_strict.csv"
    if eff.exists():
        e = pd.read_csv(eff)
        groups = [("xgb", "XGBoost, re-tuned\nfor each data set"), ("xgb_fixed", "XGBoost, hyperparameters\nfixed (tuned on 'excluded')"),
                  ("ols_P", "OLS on log\nprecipitation")]
        groups = [g for g in groups if g[0] in set(e["model"])]
        pairs = e[["train", "test"]].drop_duplicates().values.tolist()
        mk = {"asis": ("o", "white", INK2), "exclude": ("o", INK, INK), "corrected": ("^", INK2, INK2)}
        OFF = 1.5
        for gi, (m, lab) in enumerate(groups):
            xo = gi * OFF
            ax.axvline(xo, color=BASE, linewidth=0.6, zorder=0)
            ax.text(xo, -0.95, lab, fontsize=6, ha="center", va="bottom", fontweight="bold", color=INK)
            for i, (T, E) in enumerate(pairs):
                for p, dy in [("asis", -0.17), ("exclude", 0.0), ("corrected", 0.17)]:
                    r = e[(e["train"] == T) & (e["test"] == E) & (e["model"] == m) & (e["policy"] == p)]
                    if r.empty:
                        continue
                    r = r.iloc[0]
                    marker, fc, ec = mk[p]
                    ax.plot([r["r2_lo"] + xo, r["r2_hi"] + xo], [i + dy, i + dy], color="#d6d5cf", linewidth=1.4, zorder=1)
                    ax.plot(r["r2"] + xo, i + dy, marker=marker, markerfacecolor=fc, markeredgecolor=ec,
                            markersize=4, linestyle="", zorder=3)
        ax.set_yticks(range(len(pairs)))
        ax.set_yticklabels([f"{ABBR[T]} $\\rightarrow$ {ABBR[E]}" for T, E in pairs], fontsize=6.5)
        ax.set_ylim(len(pairs) - 0.5, -1.0)
        ticks = [-0.4, 0, 0.4]
        ax.set_xticks([t + gi * OFF for gi in range(len(groups)) for t in ticks])
        ax.set_xticklabels([f"{t:+.1f}" for _ in groups for t in ticks], fontsize=6)
        ax.set_xlim(-0.6, (len(groups) - 1) * OFF + 0.6)
        for gi in range(1, len(groups)):
            ax.axvline(gi * OFF - OFF / 2, color=GRID, linewidth=0.8)
        ax.set_xlabel("Transfer R$^2$ (grey bar = 95% bootstrap interval)", fontsize=6.5)
        hs = [Line2D([], [], marker=mk[p][0], markerfacecolor=mk[p][1], markeredgecolor=mk[p][2], linestyle="",
                     markersize=4, label=lab) for p, lab in [("asis", "flagged records kept as-is"),
                                                            ("exclude", "flagged records excluded (Step 0 default)"),
                                                            ("corrected", "high/medium-confidence fixes applied, rest excluded")]]
        ax.legend(handles=hs, fontsize=5.6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3)
        ax.set_title("b  Effect of the flagged records on transfer skill (strict variant)", loc="left", fontsize=8, pad=22)
        ax.grid(axis="x", color=GRID, linewidth=0.3)
    save(fig, "fig3_a3_flagged_map")


if __name__ == "__main__":
    C.set_style()
    for v in ["strict", "incl_missing"]:
        fig1(v)
        fig2(v)
    fig3()
