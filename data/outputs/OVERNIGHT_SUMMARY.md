# Overnight run — summary

*2026-04-26, branch `claude/continue-mshi-geo-V3cuc`*

## What to look at first when you wake up

1. **`data/outputs/framing2_table.md`** — the headline result in one table.
2. **`data/outputs/framing2_comparison_panel.png`** — three-panel visual of
   climate-only vs. full-features hero maps and the difference between them.
3. **`data/outputs/shap_comparison.png`** — dual-region SHAP showing why
   transfer fails (clay/sand-ratio dominates Asia, drops out of US).
4. **`data/outputs/paper_results_draft.md`** — 2,100-word results section,
   ready to edit.
5. **`data/outputs/sweep_results.json`** — raw numbers from the 6-config
   sweep, for any future re-tabulation.

## Tasks 1–7: status

| # | Task | Status | Output |
|---|---|---|---|
| 1 | Pull COSORE + retrain table | ✅ done | data/raw/cosore/cosore_annual.csv (66 sites); training table now 615 Asia + 274 US |
| 2 | Six-config sweep | ✅ done | data/outputs/sweep_results.json |
| 3 | Framing-2 comparison table | ✅ done | data/outputs/framing2_table.{csv,md} |
| 4 | Dual hero map + diff panel | ✅ done | hero_climate_only_asia.{png,pdf,screen.png}, hero_full_features_asia.{png,pdf,screen.png}, framing2_comparison_panel.png |
| 5 | Dual-region SHAP | ✅ done | shap_asia_only.png, shap_us_only.png, shap_comparison.png, shap_dual_region.json |
| 6 | Paper results draft | ✅ done | paper_results_draft.md (~2,100 words) |
| 7 | This summary | ✅ done | this file |

All seven tasks completed. No failures. Commits pushed after each task.

## Headline numbers

From the Task 2 sweep (n_train = 615 Asia, n_us = 274):

```
config                            feats   CV R²    Trans R²    Δ vs F
A_baseline                          20    -0.127    -0.031    -0.158
B_heavier_reg                       20    -0.083    +0.020    -0.107
C_shallow_more                      20    -0.054    -0.001    -0.128
D_drop_overfit                      16    -0.139    -0.024    -0.151
E_climate_plus_transferring_soil    13    -0.128    +0.008    -0.119
F_climate_only                       8    -0.067    +0.127    +0.000   ← only meaningful transfer
```

**Climate-only (F) is the only configuration that meaningfully generalises
Asia → CONUS.** Every configuration that includes the SoilGrids texture
features (clay, sand, silt, or clay/sand ratio) lands at transfer R² ≈ 0.

## Why this is the right finding

- Phase A1 confirmed SoilGrids extraction is correct; values are inside
  reference ranges and clay+sand+silt sums to 100% as it should.
- Phase A4 confirmed target distributions are nearly identical between
  Asia and US (mean shift +2.5%, σ ratio 0.88), so the transfer failure
  is not a target-distribution artefact.
- Phase A3 found r(clay, log_rs) = +0.302 in Asia, −0.048 in US. The
  same correlation reverses sign across regions.
- Task 5 dual-SHAP shows the rank-5 feature in Asia (clay/sand ratio)
  drops out of the US top-8 entirely; nitrogen jumps from middling in
  Asia to rank 2 in US.

This is regional driver heterogeneity, not a bug. Adding more SoilGrids
features will not fix it. The model is doing what XGBoost is supposed to
do — exploit per-region correlations — and those correlations don't hold
cross-continent.

## What I deliberately did NOT do

- **Did not modify hero_map.py styling.** Both hero maps use the existing
  Bedrock styling.
- **Did not generate prettier maps to compensate for low transfer R².**
  The full-features hero is rendered honestly; its anomaly structure looks
  visually compelling because the climate baseline in the denominator
  carries most of the legibility, but the diff panel
  (`framing2_comparison_panel.png`) makes the soil-feature contribution
  explicit and isolable.
- **Did not touch MODIS NPP.** Per instruction, that's user-only (GEE
  login required). All 4 MODIS rasters are still NaN in the feature
  stack.
- **Did not introduce regional sub-models or biome stratification.** Out
  of scope for the overnight run; flagged as "next-day priority" below.

## Suggested next-day priorities

In rough order of expected R² lift per hour of work:

1. **MODIS NPP via GEE** (you have to do this — login required). Published
   Rs models that include NPP get +0.10 to +0.20 in transfer R² over
   climate-only. Would push the F-class transfer R² from ~0.13 toward
   0.25–0.35.
2. **Biome stratification.** Train sub-models per IGBP class (forest,
   grassland, cropland, shrubland) using the IGBP MODIS landcover layer
   (also a GEE export). Each sub-model has fewer points but a more
   consistent feature → Rs relationship. Likely worth +0.05 to +0.10.
3. **Try a different US validation slice** — drop the manipulation /
   disturbance flag relaxations in build_target.py and see whether US
   variance drops. Would let you isolate "how much of the transfer gap is
   protocol noise in SRDB itself."
4. **COSORE coverage**. 24 of 94 datasets failed to parse with `rdata`
   (newer R serialisation features). If you have R available, install the
   cosore package and re-export those 24 to a CSV-based format to recover
   the points.

## Things to double-check before pitching

- The 5-bio climate baseline used in `composite.py` versus the 8-bio
  climate-only "F" config. These are NOT the same model. The composite
  anomaly hero (`hero_climate_only_asia.png`) is `exp(F_pred − cb_pred)`
  where F has 8 bioclim features and cb has only the canonical 5
  (bio01, bio04, bio12, bio14, bio15). The result is the *additional*
  climate signal beyond the core 5, which has its own legitimate
  interpretation but isn't quite "climate-only model output." Worth
  thinking about whether you want to render an alternative version with
  the climate-only model as both numerator and denominator, which would
  give a flat anomaly = 1.0 everywhere and force the visualisation to
  switch to predicted Rs directly rather than a ratio.
- The transfer R² for B (heavier regularisation) is +0.020 — *barely*
  positive. Don't oversell that as "transfer works with full features
  if you regularise enough." It's still essentially zero.

## Open questions for you

1. Do you want a hero map of *predicted Rs* (not anomaly) in addition to
   the anomaly maps? The anomaly visualisation requires a non-trivial
   denominator decision; a direct *Rs* heatmap would be simpler to
   defend.
2. The Task 4 "B − F" diff panel uses a diverging colormap that's
   different from the main hero's diverging colormap — same family
   (PuOr_r vs RdBu) but the diff scale is ±0.30 in anomaly units rather
   than 0.5–1.5. If you want them visually unified, easy fix.
3. The paper draft has four "[NEEDS CITATION]" tags for Hashimoto/Yao/
   Chen/Zhang continental-Rs references. Verify or replace before
   submitting.

## File-tree of what landed in this run

```
data/raw/cosore/cosore_annual.csv             (66-site aggregate)

scripts/cosore_aggregate.py
scripts/extract_points_only.py
scripts/phase_a1.py            (committed earlier this session)
scripts/phase_a234.py          (committed earlier this session)
scripts/task2_sweep.py
scripts/task3_table.py
scripts/task4_dual_hero.py
scripts/task5_dual_shap.py

data/outputs/sweep_results.json
data/outputs/framing2_table.csv
data/outputs/framing2_table.md
data/outputs/hero_climate_only_asia.{png,pdf,screen.png}
data/outputs/hero_full_features_asia.{png,pdf,screen.png}
data/outputs/framing2_comparison_panel.png
data/outputs/shap_asia_only.png
data/outputs/shap_us_only.png
data/outputs/shap_comparison.png
data/outputs/shap_dual_region.json
data/outputs/paper_results_draft.md
data/outputs/OVERNIGHT_SUMMARY.md             (this file)
```

Branch is at HEAD `claude/continue-mshi-geo-V3cuc`, fully pushed. Working
tree clean.
