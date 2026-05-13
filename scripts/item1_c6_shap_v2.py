"""Item 1 Checkpoint 6 (part 1) — side-by-side SHAP comparison.

Builds shap_v2_comparison.png — F (Run A) vs F+NPP (Item 1) bar charts
showing mean |SHAP| per feature. Visualises whether NPP changes the
top-feature picture.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "outputs"

# Bedrock palette
C = {"paper": "#FAF8F5", "ink": "#0E1116", "ink_soft": "#3A4048",
     "rule": "#C8CCD2", "accent": "#A4221A", "blue": "#1F4068"}

# Load F+NPP SHAP from Item 1
fnpp_shap = json.load(open(OUT / "F_NPP_shap.json"))["ranking"]

# Re-compute F SHAP fresh on the v1 training data for clean comparison
asia = pd.read_parquet(PROC / "training_features_v2.parquet")  # has same Asia points
TARGET = "log_rs_annual"
F_FEATS = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)

a_F = asia.dropna(subset=[TARGET] + F_FEATS).reset_index(drop=True)
print(f"F SHAP regen — n_train = {len(a_F)}")
m = xgb.XGBRegressor(**PARAMS_F)
m.fit(a_F[F_FEATS].to_numpy("float32"), a_F[TARGET].to_numpy("float32"))
explainer = shap.TreeExplainer(m)
Xs = a_F[F_FEATS].sample(min(800, len(a_F)), random_state=42)
sv = explainer.shap_values(Xs)
F_importance = np.abs(sv).mean(axis=0)
F_order = np.argsort(F_importance)[::-1]
F_ranking = [{"feature": F_FEATS[F_order[i]],
              "mean_abs_shap": float(F_importance[F_order[i]])}
             for i in range(len(F_FEATS))]

# Two-panel bar chart
fig, axes = plt.subplots(1, 2, figsize=(14, 6),
                         gridspec_kw={"wspace": 0.35},
                         facecolor=C["paper"])

def bar_panel(ax, ranking, title, accent_features=None, colour=C["blue"]):
    ax.set_facecolor(C["paper"])
    accent_features = accent_features or []
    feats = [r["feature"] for r in ranking]
    vals = [r["mean_abs_shap"] for r in ranking]
    y = np.arange(len(feats))[::-1]
    colors = [C["accent"] if f in accent_features else colour for f in feats]
    ax.barh(y, vals, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(feats, fontsize=9)
    ax.set_xlabel("mean |SHAP|", fontsize=10, color=C["ink_soft"])
    ax.tick_params(axis="x", labelsize=8, colors=C["ink_soft"])
    ax.set_title(title, fontsize=11.5, color=C["ink"], weight="bold", pad=10, loc="left")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(C["rule"])
    # Annotate values
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, y[i], f"{v:.3f}",
                fontsize=8, color=C["ink_soft"], va="center")

bar_panel(axes[0], F_ranking,
          "F:  climate only (8 bioclim)\ntransfer R² = +0.127  (CI excl. 0)",
          colour=C["blue"])
bar_panel(axes[1], fnpp_shap,
          "F+NPP:  + 4 MODIS continuous (12 features)\ntransfer R² = +0.145  (CI excl. 0)",
          accent_features={"npp", "lst_day", "lst_night", "lst_diurnal_range"},
          colour=C["blue"])

fig.suptitle(
    "MODIS NPP becomes the rank-1 driver — but bio12, bio04 stay in the climate top-3",
    fontsize=13, color=C["ink"], weight="bold", y=0.99,
)
fig.subplots_adjust(top=0.88, bottom=0.10, left=0.10, right=0.97)
fig.savefig(OUT / "shap_v2_comparison.png", dpi=300, facecolor=C["paper"])
fig.savefig(OUT / "shap_v2_comparison_screen.png", dpi=160, facecolor=C["paper"])
plt.close(fig)
print(f"wrote {OUT/'shap_v2_comparison.png'}")
print(f"wrote {OUT/'shap_v2_comparison_screen.png'}")

# Save the F ranking so the panel script can re-use
(OUT / "F_shap_ranking_regen.json").write_text(json.dumps({
    "config_name": "F_climate_only",
    "ranking": F_ranking,
}, indent=2))
