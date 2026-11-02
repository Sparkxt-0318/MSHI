"""Task 5 — dual-region SHAP comparison.

Trains two parallel models with the SAME hyperparameters and feature list:
  - asia_model on the Asia training set, SHAP computed on Asia samples
  - us_model   on the US validation set, SHAP computed on US samples

The asymmetry in mean |SHAP| ranking is the visual proof that the same
features drive log_rs_annual differently in the two regions, which is the
mechanistic reason transfer R² stays near zero with soil features included.

Outputs:
  data/outputs/shap_asia_only.png        (matplotlib SHAP summary, Asia)
  data/outputs/shap_us_only.png          (matplotlib SHAP summary, US)
  data/outputs/shap_comparison.png       (side-by-side mean |SHAP| bar chart)
  data/outputs/shap_dual_region.json     (numerical rankings)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"

asia = pd.read_parquet(PROC / "training_features.parquet")
us = pd.read_parquet(PROC / "us_validation_features.parquet")
target = "log_rs_annual"
drop = {target, "rs_annual", "longitude", "latitude", "site_id", "source", "region"}
FEATS = [c for c in asia.columns if c not in drop]
print(f"features ({len(FEATS)}): {FEATS}")

PARAMS = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
              subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
              reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)


def fit_and_shap(name, df):
    df = df.dropna(subset=[target] + FEATS).reset_index(drop=True)
    X = df[FEATS]; y = df[target].to_numpy("float32")
    print(f"[{name}] training on n={len(df)}")
    m = xgb.XGBRegressor(**PARAMS)
    m.fit(X.to_numpy("float32"), y)

    explainer = shap.TreeExplainer(m)
    Xs = X.sample(min(800, len(df)), random_state=42)
    sv = explainer.shap_values(Xs)

    # Save shap summary plot
    plt.figure(figsize=(9, 6))
    shap.summary_plot(sv, Xs, show=False, max_display=20)
    plt.title(f"SHAP summary — {name} (n={len(df)})", fontsize=10)
    plt.tight_layout()
    out = OUT / f"shap_{name.lower().replace(' ', '_')}_only.png"
    plt.savefig(out, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"  → {out}")

    importance = np.abs(sv).mean(axis=0)
    df_imp = (pd.DataFrame({"feature": list(Xs.columns), "mean_abs_shap": importance})
              .sort_values("mean_abs_shap", ascending=False).reset_index(drop=True))
    return df_imp


df_asia = fit_and_shap("Asia", asia)
df_us = fit_and_shap("US", us)

# Comparison bar chart
merged = (df_asia.rename(columns={"mean_abs_shap": "asia"})
          .merge(df_us.rename(columns={"mean_abs_shap": "us"}), on="feature"))
# rank by asia importance (descending)
merged = merged.sort_values("asia", ascending=False).reset_index(drop=True)

fig, ax = plt.subplots(figsize=(11, 7))
n = len(merged)
y_pos = np.arange(n)
width = 0.4
ax.barh(y_pos - width/2, merged["asia"], height=width, color="#5B7FB8",
        label="Asia (n=%d)" % len(asia.dropna(subset=[target] + FEATS)),
        edgecolor="white")
ax.barh(y_pos + width/2, merged["us"], height=width, color="#C26060",
        label="US (n=%d)" % len(us.dropna(subset=[target] + FEATS)),
        edgecolor="white")
ax.set_yticks(y_pos)
ax.set_yticklabels(merged["feature"])
ax.invert_yaxis()
ax.set_xlabel("mean |SHAP| (log_rs_annual prediction)")
ax.set_title(
    "Per-region driver heterogeneity\n"
    "Same hyperparameters, same feature list — drivers differ",
    fontsize=11,
)
ax.legend(loc="lower right", frameon=False)
ax.grid(axis="x", alpha=0.25)
ax.set_axisbelow(True)
plt.tight_layout()
out = OUT / "shap_comparison.png"
plt.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close()
print(f"  → {out}")

(OUT / "shap_dual_region.json").write_text(json.dumps({
    "asia_n_train": int(len(asia.dropna(subset=[target] + FEATS))),
    "us_n_train":   int(len(us.dropna(subset=[target] + FEATS))),
    "feature_set": FEATS,
    "params": PARAMS,
    "asia_ranking":  df_asia.to_dict(orient="records"),
    "us_ranking":    df_us.to_dict(orient="records"),
}, indent=2, default=float))

print("\nTop-8 by region:")
print(f"{'rank':>4s}  {'asia':<22s} {'asia mean|SHAP|':>16s}  {'us':<22s} {'us mean|SHAP|':>14s}")
for i in range(min(8, len(df_asia), len(df_us))):
    a = df_asia.iloc[i]; u = df_us.iloc[i]
    print(f"{i+1:>4d}  {a.feature:<22s} {a.mean_abs_shap:>16.4f}  "
          f"{u.feature:<22s} {u.mean_abs_shap:>14.4f}")
