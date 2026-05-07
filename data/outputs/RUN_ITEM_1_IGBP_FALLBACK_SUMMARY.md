# Item 1 — IGBP-stratified fallback summary

*2026-05-05, branch `claude/item-1-modis`. User-authorised fallback
after the original Item 1 pre-flight failed (3/4 MODIS rasters were
2-byte placeholders; see `RUN_ITEM_1_BLOCKERS.md`). Six steps
completed, all commits pushed, working tree clean.*

## Three things to look at first when you wake up

1. **`data/outputs/igbp_stratification.md`** — the per-biome transfer
   table. Forest is significantly negative; grassland has the best
   point estimate (+0.275, ρ=+0.482) but its CI spans zero;
   savanna and cropland are flat. Three of four qualifying biomes
   fail to beat the cross-biome F baseline of +0.127.
2. **`data/outputs/stratification_comparison.png`** —
   forest-plot-style figure with all stratification rows on one
   x-axis (cross-biome baseline · 2 Köppen zones · 4 IGBP biomes).
   Visual proof that only the cross-biome row's CI excludes zero.
3. **`data/outputs/paper_results_draft.md`** — new §4.6 added with
   the IGBP results; §6 "regional sub-models" paragraph extended to
   cite both stratifications. No other section touched.

## Headline numbers

| Stratum | n_Asia | n_US | Transfer R² | 95 % CI | CI excl. 0 |
|---|---:|---:|---:|---|---|
| **Cross-biome F (reference)** | **600** | **272** | **+0.127** | **(+0.020, +0.212)** | **yes** |
| Köppen C (Run B)              | 247    | 89    | −0.336 | (−1.06, +0.04)   | no |
| Köppen D (Run B)              | 244    | 159   | −0.199 | (−0.39, −0.06)   | yes (negative) |
| IGBP forest                   | 187    | 82    | −0.265 | (−0.578, −0.058) | yes (negative) |
| IGBP savanna                  | 146    | 86    | −0.214 | (−0.724, +0.104) | no |
| IGBP grassland                | 83     | 34    | **+0.275** | (−0.060, +0.474) | no (spans 0) |
| IGBP cropland                 | 108    | 36    | −0.143 | (−0.472, +0.067) | no |

## What this resolved

Run B (Köppen) left the IGBP-stratified test as the open question.
The hypothesis was that land-use confounding — suggested by the
clay-Rs sign-flip in §4 (r_Asia=+0.302, r_US=−0.048) — was the
mechanism breaking transfer. If land-use was the confound, training
within a single land-cover class should clean it up.

It did not. Even with the right stratification variable, three of
four qualifying biomes fail to beat the cross-biome baseline. Forest
is particularly striking: its CI is fully below zero, meaning the
forest-only F model on Asia performs *worse* on US forest sites
than predicting the US-mean *Rs*. This is the same regression-to-mean
failure pattern observed in Köppen D.

## What's still genuinely open

**Grassland** is the one biome where stratification *might* be
working. Point estimate +0.275 is more than double the cross-biome
baseline of +0.127. Spearman ρ = +0.482 is the highest of any row in
the table — predictions and observations track in rank order much
better than they track in level. But n_us = 34 makes the bootstrap
distribution wide; the 95 % CI (−0.060, +0.474) cannot reject zero.

This is the only result that would survive scrutiny if the US
grassland sample doubled. In the IGBP-only run a doubling isn't
possible from existing SRDB+COSORE — Stell et al. 2021 already
characterise the SRDB northern-temperate-bias problem. It IS the
result that an in-situ biosensor network deployed at US grassland
sites would resolve.

## What I did NOT do

- F+NPP and Full+MODIS configs (Items 1 Checkpoints 2-3): blocked,
  3/4 MODIS rasters are placeholders. F+NPP's hypothetical lift
  on transfer R² is unknown until real NPP / LST land.
- Hero map for an MODIS-augmented model (Checkpoint 5): blocked.
- SHAP comparison panel showing F+NPP shifting the top features
  (Checkpoint 6): blocked.
- An IGBP-augmented hero map (would have been a stretch goal — the
  asia 5 km grid does not yet have landcover sampled, would have
  required ~30 min more compute).

## Files added in this run

```
data/outputs/igbp_stratification.json
data/outputs/igbp_stratification.md
data/outputs/stratification_comparison.png
data/outputs/stratification_comparison_screen.png
data/outputs/paper_results_draft.md          (modified: new §4.6 + §6 update)
data/outputs/RUN_ITEM_1_BLOCKERS.md          (committed earlier this session)
data/outputs/RUN_ITEM_1_IGBP_FALLBACK_SUMMARY.md  (this file)

data/processed/training_features.parquet     (replaced synthetic with real 615-row Asia table)
data/processed/us_validation_features.parquet (force-added; 274 rows)

scripts/igbp_step2_regen_features.py
scripts/igbp_step4_stratification.py
scripts/igbp_step5_comparison_plot.py
```

## Open questions for you

1. **Should the grassland +0.275 result enter the pitch?** Honest
   answer: only with the CI alongside it. The point estimate is the
   strongest hint that biome-targeted modelling could rescue
   transfer, but the CI does not yet support that claim. If you
   pitch grassland-only as a "promising future avenue" that's
   defensible. If you pitch it as a "we can do this with better
   stratification" claim, it isn't.
2. **Cross-zone vs within-zone in the deck.** The current deck
   (Round C) shows the cross-zone +0.127 result and the dual-region
   SHAP. Adding the stratification-comparison forest plot to slide 8
   (the Köppen slide) would visually unify the IGBP and Köppen
   findings. One commit when you authorise.
3. **MODIS rasters.** The hard blocker. Push the real
   `npp_2020_2024_mean.tif`, `lst_day_2020_2024_mean.tif`, and
   `lst_night_2020_2024_mean.tif` and Item 1's original
   Checkpoints 2-7 (F+NPP, Full+MODIS, hero, etc.) become a 2-3 hour
   re-run from this branch.

Branch `claude/item-1-modis` ready to merge or extend. Working
tree clean after this commit.
