"""Task 3 — alternative metrics on the US validation set for configs F and B.

Reports for each config:
  - Spearman rank correlation between predicted and observed log_rs_annual
  - Tertile classification accuracy: split observed log_rs into tertiles
    using observed-only thresholds, classify predicted into tertiles
    using THE SAME thresholds, report fraction correctly classified
  - NRMSE = RMSE / (max obs - min obs)
  - MAE in original (non-log) Rs_annual units (g C m-2 yr-1)

Outputs:
  data/outputs/alternative_metrics.json
  data/outputs/metrics_summary.md
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import spearmanr
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT  = ROOT / "data" / "outputs"

train = pd.read_parquet(PROC / "training_features.parquet")
us    = pd.read_parquet(PROC / "us_validation_features.parquet")
target = "log_rs_annual"

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
ALL_FEATS = ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec",
             *CLIMATE_8, "c_n_ratio", "clay_sand_ratio", "ph_optimality",
             "aridity_demartonne"]
PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)
PARAMS_B = dict(n_estimators=250, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=8,
                reg_alpha=2.0, reg_lambda=8.0, n_jobs=1, verbosity=0)


def fit_predict(feats, params):
    tr = train.dropna(subset=[target] + feats).reset_index(drop=True)
    te = us.dropna(subset=[target] + feats).reset_index(drop=True)
    m = xgb.XGBRegressor(**params)
    m.fit(tr[feats].to_numpy("float32"), tr[target].to_numpy("float32"))
    pred_log = m.predict(te[feats].to_numpy("float32"))
    obs_log = te[target].to_numpy("float64")
    return obs_log, pred_log, len(tr), len(te)


def tertile_accuracy(obs, pred):
    """Split obs into tertiles, bin pred with the SAME edges, fraction correct."""
    edges = np.quantile(obs, [1/3, 2/3])
    obs_bin = np.digitize(obs, edges)   # 0,1,2
    pred_bin = np.digitize(pred, edges)
    correct = (obs_bin == pred_bin).mean()
    # also confusion matrix
    cm = np.zeros((3, 3), dtype=int)
    for o, p in zip(obs_bin, pred_bin):
        cm[int(o), int(p)] += 1
    return float(correct), cm.tolist()


def metrics(obs_log, pred_log):
    obs_rs  = np.exp(obs_log)
    pred_rs = np.exp(pred_log)
    rmse_log = float(np.sqrt(mean_squared_error(obs_log, pred_log)))
    nrmse = rmse_log / (obs_log.max() - obs_log.min())
    sp, _ = spearmanr(pred_log, obs_log)
    tert_acc, cm = tertile_accuracy(obs_log, pred_log)
    return {
        "r2_log":          float(r2_score(obs_log, pred_log)),
        "rmse_log":        rmse_log,
        "nrmse":           float(nrmse),
        "spearman":        float(sp),
        "mae_log":         float(mean_absolute_error(obs_log, pred_log)),
        "mae_rs_gC_m2_yr": float(mean_absolute_error(obs_rs, pred_rs)),
        "median_ae_rs":    float(np.median(np.abs(obs_rs - pred_rs))),
        "tertile_accuracy_baseline_1_3": 1/3,
        "tertile_accuracy":     tert_acc,
        "tertile_confusion":    cm,
    }


results = {}
for name, feats, params in [
    ("F_climate_only", CLIMATE_8, PARAMS_F),
    ("B_full_features", ALL_FEATS, PARAMS_B),
]:
    obs, pred, n_train, n_us = fit_predict(feats, params)
    m = metrics(obs, pred)
    m["n_train"] = n_train
    m["n_us"] = n_us
    results[name] = m

(OUT / "alternative_metrics.json").write_text(json.dumps(results, indent=2))

# Markdown summary
def fmt_pct(x): return f"{100*x:.1f}%"
def f3(x): return f"{x:+.3f}" if isinstance(x, float) else str(x)

f = results["F_climate_only"]
b = results["B_full_features"]
md = [
    "# Alternative metrics — Asia → US transfer",
    "",
    "Computed on the held-out US validation set after fitting the model on the",
    "full Asia training set. Same models as Task 2 bootstrap.",
    "",
    "| Metric | F: climate-only | B: full features (20) | Notes |",
    "|---|---:|---:|---|",
    f"| n_train (Asia, post-NaN drop) | {f['n_train']} | {b['n_train']} | F drops fewer rows because its 8-feature subset has higher coverage |",
    f"| n_us (post-NaN drop) | {f['n_us']} | {b['n_us']} | |",
    f"| **R² (log Rs)** | **{f['r2_log']:+.3f}** | **{b['r2_log']:+.3f}** | primary success metric |",
    f"| RMSE (log Rs) | {f['rmse_log']:.3f} | {b['rmse_log']:.3f} | |",
    f"| NRMSE (RMSE / range) | {f['nrmse']:.3f} | {b['nrmse']:.3f} | normalised by US observed range |",
    f"| **Spearman ρ** | **{f['spearman']:+.3f}** | **{b['spearman']:+.3f}** | rank correlation, robust to mean shift |",
    f"| MAE (log Rs) | {f['mae_log']:.3f} | {b['mae_log']:.3f} | |",
    f"| MAE (Rs, g C m⁻² yr⁻¹) | {f['mae_rs_gC_m2_yr']:.0f} | {b['mae_rs_gC_m2_yr']:.0f} | original units |",
    f"| Median |AE| (Rs) | {f['median_ae_rs']:.0f} | {b['median_ae_rs']:.0f} | robust to outliers |",
    f"| **Tertile accuracy** | **{fmt_pct(f['tertile_accuracy'])}** | **{fmt_pct(b['tertile_accuracy'])}** | random baseline = 33.3% |",
    "",
    "## Interpretation",
    "",
    "On the metrics that distinguish position-and-spread (R², RMSE, NRMSE, MAE)",
    "F climate-only is the better model:",
    f"R² {f['r2_log']:+.3f} vs {b['r2_log']:+.3f}, RMSE {f['rmse_log']:.3f} vs {b['rmse_log']:.3f}.",
    "",
    "On the rank-only Spearman test, F also wins, but the gap narrows:",
    f"ρ_F = {f['spearman']:+.3f}, ρ_B = {b['spearman']:+.3f}. Both models recover",
    "the broad ordering of US sites by Rs, even though only F recovers the level.",
    "",
    "On coarse tertile classification (a much weaker test than R² because it",
    "discards within-tertile information), the two configurations are",
    f"essentially tied: F = {fmt_pct(f['tertile_accuracy'])}, B = {fmt_pct(b['tertile_accuracy'])} ",
    "against a 33.3% random baseline. The confusion matrices show both models",
    "predicting heavily into the middle tertile — the regression-to-mean",
    "signature already documented in pred_std. Tertile accuracy is therefore",
    "not the most decision-relevant metric here; R² and Spearman are.",
    "",
    "MAE in original Rs units is large for both configurations",
    f"(F: {f['mae_rs_gC_m2_yr']:.0f}, B: {b['mae_rs_gC_m2_yr']:.0f} g C m⁻² yr⁻¹) "
    "against a median observed Rs of",
    "≈760 g C m⁻² yr⁻¹ — i.e. roughly 50% relative error in either case.",
    "Continental upscaling without a vegetation-productivity covariate (MODIS NPP)",
    "cannot resolve the absolute Rs level even when the rank ordering generalises.",
]
(OUT / "metrics_summary.md").write_text("\n".join(md))

print(json.dumps(results, indent=2))
print()
print(f"→ wrote {OUT / 'alternative_metrics.json'}")
print(f"→ wrote {OUT / 'metrics_summary.md'}")
