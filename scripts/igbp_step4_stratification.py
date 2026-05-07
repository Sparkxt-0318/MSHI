"""IGBP-fallback Step 4 — biome-stratified F (climate-only) Asia → US transfer.

For each IGBP biome class with ≥ 80 Asian sites and ≥ 30 US sites, train
the F (climate-only, 8 bioclim) model on the Asia subset of that class
and evaluate on the US subset. Same hyperparameters as Run A's F config.

This is the IGBP analogue of the Köppen-Geiger stratification done in
Run B (data/outputs/koppen_stratification.json), but uses true land-
cover classes instead of climate-zone proxies.

Outputs:
    data/outputs/igbp_stratification.json
    data/outputs/igbp_stratification.md
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shap
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

# Biome buckets per the Item 1 prompt
BIOME_BUCKETS = {
    "forest":    {1, 2, 3, 4, 5},          # evergreen/deciduous/mixed forest
    "shrubland": {6, 7},                    # closed/open shrubland
    "savanna":   {8, 9},                    # woody/open savanna
    "grassland": {10},                      # grassland
    "wetland":   {11},                      # permanent wetland
    "cropland":  {12, 14},                  # cropland + cropland mosaic
    "barren":    {16},                      # barren / sparsely vegetated
}


def assign_biome(lc: pd.Series) -> pd.Series:
    out = pd.Series(["other"] * len(lc), index=lc.index, dtype=object)
    for biome, codes in BIOME_BUCKETS.items():
        out[lc.isin(codes)] = biome
    return out


def bootstrap_r2(obs, pred, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(obs)
    r2s = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r2s[i] = r2_score(obs[idx], pred[idx])
    return r2s


def run_one_biome(name, asia_sub, us_sub):
    a = asia_sub.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    u = us_sub.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    if len(a) < 80 or len(u) < 30:
        return {"skipped": True,
                "reason": f"insufficient sites (n_asia={len(a)}, n_us={len(u)})",
                "n_asia": int(len(a)), "n_us": int(len(u))}

    Xa = a[CLIMATE_8].to_numpy("float32"); ya = a[TARGET].to_numpy("float32")
    m = xgb.XGBRegressor(**PARAMS_F)
    m.fit(Xa, ya)
    Xu = u[CLIMATE_8].to_numpy("float32"); yu = u[TARGET].to_numpy("float32")
    pu = m.predict(Xu)

    boot = bootstrap_r2(yu, pu, n_boot=1000, seed=42)
    r2 = float(r2_score(yu, pu))
    rmse = float(np.sqrt(mean_squared_error(yu, pu)))
    sp, _ = spearmanr(pu, yu)

    # SHAP top-5
    try:
        explainer = shap.TreeExplainer(m)
        sv = explainer.shap_values(a[CLIMATE_8].sample(min(400, len(a)),
                                                       random_state=42))
        importance = np.abs(sv).mean(axis=0)
        order = np.argsort(importance)[::-1]
        top5 = [{"feature": CLIMATE_8[i],
                 "mean_abs_shap": float(importance[i])}
                for i in order[:5]]
    except Exception as e:
        top5 = [{"feature": "shap_failed", "mean_abs_shap": 0.0,
                 "error": str(e)}]

    return {
        "n_asia": int(len(a)),
        "n_us": int(len(u)),
        "transfer_r2": r2,
        "transfer_rmse": rmse,
        "spearman": float(sp),
        "bias": float(np.mean(pu - yu)),
        "bootstrap_median": float(np.median(boot)),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "ci_excludes_zero": bool(np.quantile(boot, 0.025) > 0
                                 or np.quantile(boot, 0.975) < 0),
        "top_shap": top5,
        "method": "F (climate-only, 8 bioclim)",
    }


def main():
    asia = pd.read_parquet(PROC / "training_features.parquet")
    us = pd.read_parquet(PROC / "us_validation_features.parquet")
    print(f"Asia: {asia.shape}, US: {us.shape}")

    if "landcover" not in asia.columns or "landcover" not in us.columns:
        raise SystemExit("landcover column missing — run Step 2 first")

    asia["biome"] = assign_biome(asia["landcover"].astype("float").astype("Int64"))
    us["biome"] = assign_biome(us["landcover"].astype("float").astype("Int64"))

    asia_counts = asia["biome"].value_counts().to_dict()
    us_counts = us["biome"].value_counts().to_dict()
    print("\nIGBP biome counts:")
    biomes = list(BIOME_BUCKETS.keys()) + ["other"]
    for b in biomes:
        print(f"  {b:<10} asia={asia_counts.get(b,0):>3}  us={us_counts.get(b,0):>3}")

    # Per-biome stratified analysis
    results = {}
    for biome in BIOME_BUCKETS.keys():
        a_sub = asia[asia["biome"] == biome]
        u_sub = us[us["biome"] == biome]
        r = run_one_biome(biome, a_sub, u_sub)
        results[biome] = r
        if r.get("skipped"):
            print(f"\n{biome}: SKIPPED — {r['reason']}")
        else:
            print(f"\n{biome}: n_asia={r['n_asia']}, n_us={r['n_us']}")
            print(f"  R²={r['transfer_r2']:+.3f}  CI=({r['ci_low']:+.3f}, "
                  f"{r['ci_high']:+.3f})  ρ={r['spearman']:+.3f}  "
                  f"excl0={r['ci_excludes_zero']}")
            print(f"  top SHAP: " +
                  ", ".join(f"{t['feature']}={t['mean_abs_shap']:.3f}"
                            for t in r["top_shap"]))

    # Cross-biome F baseline
    a_all = asia.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    u_all = us.dropna(subset=[TARGET] + CLIMATE_8).reset_index(drop=True)
    m = xgb.XGBRegressor(**PARAMS_F)
    m.fit(a_all[CLIMATE_8].to_numpy("float32"), a_all[TARGET].to_numpy("float32"))
    pu = m.predict(u_all[CLIMATE_8].to_numpy("float32"))
    boot = bootstrap_r2(u_all[TARGET].to_numpy(), pu, n_boot=1000, seed=42)
    results["_baseline_F_all_biomes"] = {
        "n_asia": int(len(a_all)),
        "n_us": int(len(u_all)),
        "transfer_r2": float(r2_score(u_all[TARGET].to_numpy(), pu)),
        "bootstrap_median": float(np.median(boot)),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "ci_excludes_zero": bool(np.quantile(boot, 0.025) > 0),
    }
    print(f"\n[baseline] full Asia → full US, F: "
          f"R² = {results['_baseline_F_all_biomes']['transfer_r2']:+.3f}, "
          f"CI = ({results['_baseline_F_all_biomes']['ci_low']:+.3f}, "
          f"{results['_baseline_F_all_biomes']['ci_high']:+.3f})")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "igbp_stratification.json").write_text(json.dumps({
        "asia_counts": asia_counts,
        "us_counts": us_counts,
        "buckets": {k: list(v) for k, v in BIOME_BUCKETS.items()},
        "results": results,
    }, indent=2))
    print(f"\nwrote {OUT/'igbp_stratification.json'}")

    # Markdown summary
    md = [
        "# IGBP-stratified F (climate-only) Asia → US transfer",
        "",
        "*Built 2026-05-05 on branch `claude/item-1-modis` as the **IGBP "
        "fallback** authorised by the user after Item 1's pre-flight failed "
        "(NPP / LST_day / LST_night placeholders). The MODIS landcover "
        "raster IS real; this analysis uses it.*",
        "",
        "## What this answers",
        "",
        "Run B asked: does within-class stratification rescue cross-",
        "continental Rs transfer? Run B used Köppen-Geiger climate zones",
        "(computable without MODIS) and found within-zone transfer was",
        "*worse* than the cross-zone baseline. The IGBP-stratified test",
        "is the analogous experiment using **land-cover classes** instead",
        "of climate zones — addressing the original question whether the",
        "land-use confound (suspected from the clay-Rs sign-flip in",
        "Section 4 of the paper) is what breaks transfer.",
        "",
        "## Bucket definitions (IGBP top-level)",
        "",
        "| bucket | IGBP codes | semantics |",
        "|---|---|---|",
        "| forest    | 1, 2, 3, 4, 5 | evergreen/deciduous/mixed forest |",
        "| shrubland | 6, 7         | closed / open shrubland |",
        "| savanna   | 8, 9         | woody / open savanna |",
        "| grassland | 10           | grassland |",
        "| wetland   | 11           | permanent wetland |",
        "| cropland  | 12, 14       | cropland + cropland-natural mosaic |",
        "| barren    | 16           | barren / sparsely vegetated |",
        "| other     | 13, 15, 17, NaN | urban / snow-ice / water / unsampled |",
        "",
        "## Site counts",
        "",
        "| bucket | Asia | US |",
        "|---|---:|---:|",
    ]
    for b in BIOME_BUCKETS.keys():
        md.append(f"| {b} | {asia_counts.get(b, 0)} | {us_counts.get(b, 0)} |")
    md.append(f"| other | {asia_counts.get('other', 0)} | {us_counts.get('other', 0)} |")
    md += [
        "",
        "## Per-biome transfer (F, 8 bioclim, 1000-iter bootstrap CI)",
        "",
        "| biome | n_Asia | n_US | Transfer R² | 95% CI | Excludes 0? | Spearman ρ |",
        "|---|---:|---:|---:|---|---|---:|",
    ]
    for b in BIOME_BUCKETS.keys():
        r = results[b]
        if r.get("skipped"):
            md.append(f"| {b} | {r.get('n_asia', '—')} | {r.get('n_us', '—')} | "
                      f"— | — | — | (skipped: {r['reason']}) |")
        else:
            md.append(
                f"| {b} | {r['n_asia']} | {r['n_us']} | "
                f"{r['transfer_r2']:+.3f} | "
                f"({r['ci_low']:+.3f}, {r['ci_high']:+.3f}) | "
                f"{'**yes**' if r['ci_excludes_zero'] else 'no'} | "
                f"{r['spearman']:+.3f} |"
            )
    base = results["_baseline_F_all_biomes"]
    md += [
        "",
        f"**Cross-biome F baseline** (whole-Asia → whole-US, no stratification): "
        f"R² = {base['transfer_r2']:+.3f}, "
        f"CI = ({base['ci_low']:+.3f}, {base['ci_high']:+.3f}). "
        f"This is the same number reported in Run A's bootstrap_ci.json "
        "(re-confirmed on this branch).",
        "",
        "## How to read",
        "",
        "Two questions per row:",
        "",
        "1. **Does within-biome transfer beat the cross-biome baseline?** A",
        "   biome where land-use confounding masks the cross-region signal",
        "   should outperform the cross-biome F baseline once that biome is",
        "   isolated (homogeneous sub-models).",
        "",
        "2. **Does the within-biome 95% CI exclude zero?** A biome with a",
        "   positive point estimate but a CI spanning zero has not",
        "   established significant transfer.",
        "",
        "## Caveat about *F* vs *F+NPP* and Full+MODIS",
        "",
        "This analysis trains the *F* configuration only — climate features",
        "alone. It does not test whether NPP-augmented (F+NPP) or full-",
        "feature (Full+MODIS) models would have within-biome transfer that",
        "improves on the cross-biome baseline, because three of the four",
        "MODIS rasters needed for those configurations are 2-byte placeholders",
        "on this branch (see `RUN_ITEM_1_BLOCKERS.md`). Once real NPP and",
        "LST rasters are pushed, the F+NPP-stratified and Full+MODIS-",
        "stratified versions of this analysis become a one-script run.",
    ]
    (OUT / "igbp_stratification.md").write_text("\n".join(md))
    print(f"wrote {OUT/'igbp_stratification.md'}")


if __name__ == "__main__":
    main()
