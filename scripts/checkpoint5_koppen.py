"""Checkpoint 5 substitute — Köppen-Geiger climate-zone stratification.

Used in place of IGBP biome stratification (which would require MODIS
land-cover, currently a hard blocker — see RUN_B_BLOCKERS.md).

Köppen-Geiger top-level classes are computable directly from the
WorldClim bioclim variables we already have on disk. We use:
    A (tropical):    bio06 (T_coldest_month) ≥ 18 °C
    B (arid):        bio12 < 400 mm AND bio14 < 30 mm
                     (heuristic; standard B-class rule needs monthly
                      precipitation seasonality which we don't have)
    C (temperate):   −3 ≤ bio06 < 18 AND bio05 ≥ 10 (and not B)
    D (continental): bio06 < −3        AND bio05 ≥ 10 (and not B)
    E (polar):       bio05 < 10

Per zone, if Asia ≥ 80 sites AND US ≥ 30 sites, we train the F
(climate-only, 8 bioclim) model on the Asia subset and test on the US
subset. Same hyperparameters as Run A. Bootstrap 95% CI uses 1000
iterations to save compute.

Outputs:
    data/outputs/koppen_stratification.json
    data/outputs/koppen_stratification.md
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "outputs"

CLIMATE_8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
TARGET = "log_rs_annual"
PARAMS_F = dict(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.70, colsample_bytree=0.85, min_child_weight=6,
                reg_alpha=0.1, reg_lambda=2.0, n_jobs=1, verbosity=0)


def koppen_class(row) -> str:
    """Top-level Köppen class from bioclim variables. Returns A/B/C/D/E or 'unk'."""
    bio05 = row.get("bio05")
    bio06 = row.get("bio06")
    bio12 = row.get("bio12")
    bio14 = row.get("bio14")
    if pd.isna(bio05) or pd.isna(bio06) or pd.isna(bio12) or pd.isna(bio14):
        return "unk"
    # Polar — warmest month below 10 °C
    if bio05 < 10:
        return "E"
    # Arid — heuristic: annual precip < 400 mm AND driest month < 30 mm
    if bio12 < 400 and bio14 < 30:
        return "B"
    # Tropical — coldest month >= 18 °C
    if bio06 >= 18:
        return "A"
    # Temperate — coldest month between -3 and 18 °C
    if bio06 >= -3:
        return "C"
    # Continental — coldest month below -3 °C
    return "D"


def bootstrap_r2(obs, pred, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(obs)
    r2s = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r2s[i] = r2_score(obs[idx], pred[idx])
    return r2s


def main() -> int:
    asia = pd.read_parquet(PROC / "training_features.parquet")
    us = pd.read_parquet(PROC / "us_validation_features.parquet")

    asia["koppen"] = asia.apply(koppen_class, axis=1)
    us["koppen"] = us.apply(koppen_class, axis=1)

    asia_counts = asia["koppen"].value_counts().to_dict()
    us_counts = us["koppen"].value_counts().to_dict()

    print("Köppen class counts:")
    print(f"  {'class':<6} {'asia':>6} {'us':>6}")
    classes = sorted(set(list(asia_counts) + list(us_counts)))
    for c in classes:
        print(f"  {c:<6} {asia_counts.get(c, 0):>6} {us_counts.get(c, 0):>6}")

    results = {}
    for c in ["A", "B", "C", "D", "E"]:
        n_a, n_u = asia_counts.get(c, 0), us_counts.get(c, 0)
        if n_a < 80 or n_u < 30:
            results[c] = {
                "skipped": True,
                "reason": f"insufficient sites (n_asia={n_a}, n_us={n_u})",
                "n_asia_total": int(n_a), "n_us_total": int(n_u),
            }
            continue

        a = asia[asia["koppen"] == c].dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
        u = us[us["koppen"] == c].dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)

        X = a[CLIMATE_8].to_numpy("float32"); y = a[TARGET].to_numpy("float32")
        m = xgb.XGBRegressor(**PARAMS_F)
        m.fit(X, y)

        Xu = u[CLIMATE_8].to_numpy("float32"); yu = u[TARGET].to_numpy("float32")
        pu = m.predict(Xu)
        boot = bootstrap_r2(yu, pu, n_boot=1000, seed=42)

        # SHAP top-5 features
        try:
            import shap
            explainer = shap.TreeExplainer(m)
            sv = explainer.shap_values(a[CLIMATE_8].sample(min(400, len(a)), random_state=42))
            importance = np.abs(sv).mean(axis=0)
            order = np.argsort(importance)[::-1]
            top_shap = [{"feature": CLIMATE_8[i], "mean_abs_shap": float(importance[i])}
                        for i in order[:5]]
        except Exception as e:
            top_shap = [{"feature": "shap_failed", "mean_abs_shap": 0.0}]
            print(f"  shap error in {c}: {e}")

        sp, _ = spearmanr(pu, yu)
        results[c] = {
            "n_asia": int(len(a)),
            "n_us": int(len(u)),
            "transfer_r2": float(r2_score(yu, pu)),
            "bootstrap_median": float(np.median(boot)),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "ci_excludes_zero": bool(np.quantile(boot, 0.025) > 0
                                     or np.quantile(boot, 0.975) < 0),
            "transfer_rmse": float(np.sqrt(mean_squared_error(yu, pu))),
            "spearman": float(sp),
            "bias": float(np.mean(pu - yu)),
            "top_shap": top_shap,
            "method": "F (climate-only, 8 bioclim)",
        }
        print(f"\nKöppen {c}: n_asia={len(a)} n_us={len(u)}  "
              f"transfer R²={results[c]['transfer_r2']:+.3f}  "
              f"95% CI=({results[c]['ci_low']:+.3f}, {results[c]['ci_high']:+.3f})  "
              f"ρ={sp:+.3f}")

    # Cross-zone (full Asia → full US, F model) for reference
    a_all = asia.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    u_all = us.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    m = xgb.XGBRegressor(**PARAMS_F)
    m.fit(a_all[CLIMATE_8].to_numpy("float32"), a_all[TARGET].to_numpy("float32"))
    pu = m.predict(u_all[CLIMATE_8].to_numpy("float32"))
    boot = bootstrap_r2(u_all[TARGET].to_numpy(), pu, n_boot=1000, seed=42)
    results["_baseline_F_all_zones"] = {
        "n_asia": int(len(a_all)),
        "n_us": int(len(u_all)),
        "transfer_r2": float(r2_score(u_all[TARGET].to_numpy(), pu)),
        "bootstrap_median": float(np.median(boot)),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
    }
    print(f"\n[baseline] Full Asia → full US, F model: "
          f"R²={results['_baseline_F_all_zones']['transfer_r2']:+.3f} "
          f"CI=({results['_baseline_F_all_zones']['ci_low']:+.3f}, "
          f"{results['_baseline_F_all_zones']['ci_high']:+.3f})")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "koppen_stratification.json").write_text(
        json.dumps({"asia_counts": asia_counts, "us_counts": us_counts,
                    "results": results}, indent=2))
    print(f"\n→ wrote {OUT / 'koppen_stratification.json'}")

    # Markdown summary
    md = [
        "# Köppen-Geiger climate-zone stratification",
        "",
        "*Substitute for IGBP biome stratification while MODIS land-cover is "
        "blocked. See `RUN_B_BLOCKERS.md`.*",
        "",
        "Köppen top-level classes computed from WorldClim bio05, bio06, bio12, "
        "bio14. Per zone with ≥80 Asia training sites and ≥30 US validation "
        "sites, the F (climate-only, 8 bioclim features) model is trained on "
        "the Asia subset and tested on the US subset.",
        "",
        "## Class counts",
        "",
        "| Class | Asia | US | Description |",
        "|---|---:|---:|---|",
    ]
    desc = {"A": "Tropical (coldest month ≥ 18 °C)",
            "B": "Arid (heuristic: P_ann < 400 AND driest-month < 30 mm)",
            "C": "Temperate (coldest month −3…18 °C; warmest ≥ 10 °C)",
            "D": "Continental (coldest month < −3 °C; warmest ≥ 10 °C)",
            "E": "Polar (warmest month < 10 °C)"}
    for c in ["A", "B", "C", "D", "E"]:
        md.append(f"| {c} | {asia_counts.get(c, 0)} | {us_counts.get(c, 0)} | {desc[c]} |")
    md.append("")

    md += [
        "## Per-zone transfer results",
        "",
        "| Zone | n_Asia | n_US | Transfer R² | 95% CI | Excludes 0? | Spearman ρ |",
        "|---|---:|---:|---:|---|---|---:|",
    ]
    for c in ["A", "B", "C", "D", "E"]:
        r = results[c]
        if r.get("skipped"):
            md.append(f"| {c} | — | — | — | — | — | (skipped: {r['reason']}) |")
        else:
            md.append(
                f"| {c} | {r['n_asia']} | {r['n_us']} | "
                f"{r['transfer_r2']:+.3f} | "
                f"({r['ci_low']:+.3f}, {r['ci_high']:+.3f}) | "
                f"{'**yes**' if r['ci_excludes_zero'] else 'no'} | "
                f"{r['spearman']:+.3f} |"
            )
    md += [
        "",
        f"**Cross-zone F baseline** (whole-Asia → whole-US, no stratification): "
        f"R² = {results['_baseline_F_all_zones']['transfer_r2']:+.3f}, "
        f"CI = ({results['_baseline_F_all_zones']['ci_low']:+.3f}, "
        f"{results['_baseline_F_all_zones']['ci_high']:+.3f}).",
        "",
        "## Reading",
        "",
        "Two analytical questions for each Köppen zone:",
        "",
        "1. **Does within-zone transfer beat the cross-zone baseline?** A zone "
        "where the cross-continent feature → Rs relationship is more stable "
        "should outperform the cross-zone F model (which has to average over "
        "all zones).",
        "",
        "2. **Does within-zone transfer's 95% CI exclude zero?** This is the "
        "honest sufficient-evidence test. A zone where the CI includes zero "
        "did not establish significant transfer, even if the point estimate "
        "is positive.",
        "",
        "## Caveat",
        "",
        "Köppen zones aggregate over land-cover, which the IGBP scheme would "
        "have separated. A `forest` and a `cropland` site can fall in the same "
        "Köppen zone yet have very different soil-respiration relationships. "
        "When MODIS land-cover lands, the IGBP-stratified analysis will likely "
        "tighten the within-class results further by removing the land-use "
        "confound this analysis cannot.",
    ]
    (OUT / "koppen_stratification.md").write_text("\n".join(md))
    print(f"→ wrote {OUT / 'koppen_stratification.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
