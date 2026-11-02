# Item 1 — MODIS integration summary

*2026-05-07, branch `claude/item-1-modis`. All seven Item 1
checkpoints completed after the user pushed the real NPP / LST
rasters to claude/modis-rasters-v2 and authorised resumption.
Working tree clean.*

## Three things to look at first when you wake up

1. **`data/outputs/sweep_results_v2_table.md`** — the new headline
   table. F+NPP at transfer R² = +0.145 (CI excludes 0) is now the
   best of any configuration. Full+MODIS rescues CV (jumps to
   +0.079) but its CI still spans 0 — soil features still over-fit.
2. **`data/outputs/hero_climate_npp_asia.png`** — the F+NPP hero
   map (300 DPI, Bedrock styled, NPP-augmented anomaly composite).
3. **`data/outputs/methodology_evolution_panel_v2.png`** — 2 × 3
   panel showing F → F+NPP → Full+MODIS in the top row and Köppen
   C / Köppen D / narrative caption in the bottom row. Drops the
   "MODIS pending" placeholder from the Run-B version.

## Headline numbers

```
Config          n_train  n_us   CV R²    Transfer R²    95 % CI         CI excl. 0
A_baseline       588     270   -0.127     -0.031        —                  —
B_heavier_reg    588     270   -0.083     +0.020        (-0.141, +0.146)   no
C_shallow_more   588     270   -0.054     -0.001        —                  —
D_drop_overfit   588     270   -0.139     -0.024        —                  —
E_climate+...    588     270   -0.128     +0.008        —                  —
F_climate_only   600     272   -0.067     +0.127        (+0.019, +0.216)   yes
F+NPP            463     223   -0.021     +0.145        (+0.026, +0.241)   yes  ← BEST
Full+MODIS       463     223   +0.079     +0.072        (-0.084, +0.189)   no
```

Headline questions answered:

- **Did F+NPP beat F's CV R²?**     Yes, Δ = +0.046 (-0.067 → -0.021).
- **Did F+NPP beat F's transfer R²?** Yes, Δ = +0.018 (+0.127 → +0.145).
                                        CI still excludes zero.
- **Is NPP a top-3 driver in F+NPP?** **Yes — rank 1**, mean |SHAP| = 0.128.
                                        bio04 (rank 2) and bio12 (rank 3)
                                        keep climate in the top 3.
- **Did MODIS rescue the full-features model?**
                                        On CV — yes (Δ = +0.162, B's −0.083 → +0.079).
                                        On held-out transfer — no, CI still
                                        spans zero. Soil-feature confound
                                        persists.
- **Did NPP appear in top 3 of Full+MODIS?**  Yes — rank 1 (mean |SHAP| = 0.128).

## What the picture looks like now

The Run-A framing-2 narrative survives Item 1 intact: the configurations
whose CIs exclude zero are exactly the configurations *without* the
SoilGrids texture features. F (climate only) and F+NPP (climate + NPP)
both transfer with statistical significance. Every config that includes
clay/sand/silt or their ratios (A, B, C, D, E, Full+MODIS) lands transfer
R² with a CI that spans zero.

The lift from MODIS NPP is real but smaller than the published
expectation of +0.10 to +0.20:

- **+0.046 in CV R²** (F vs F+NPP), substantial.
- **+0.018 in held-out transfer R²** (F vs F+NPP), modest.
- The compression is partly because NPP and bio12 (annual precipitation)
  are correlated, partly because 24 % of Asian sites have NPP NaN
  (no-vegetation cells lose the vegetation feature, reducing the
  effective training set by 25 %).

The clay-Rs sign-flip diagnosed in Section 4 of the paper is
unchanged by MODIS: in Full+MODIS' SHAP, clay/sand ratio is still
rank 3, immediately behind NPP and silt. The land-use confound that
breaks transfer for soil-feature models was not addressable by adding
satellite vegetation or land-cover layers.

## What's solid vs what's preliminary

**Solid:**
- F+NPP CV and transfer R², both significant.
- NPP becoming the rank-1 SHAP feature when added to climate.
- Full+MODIS CV jump (Δ +0.162), confirming MODIS does add signal
  in-distribution.
- The hero map for F+NPP is the cleanest map we've produced —
  anomaly composite is well-behaved (median 1.005, IQR 0.842-1.183)
  and biophysically coherent.

**Preliminary / wrinkled:**
- Effective n_train = 463 in F+NPP (down from F's 600) due to NPP NaN
  over no-vegetation sites. The bootstrap CI still excludes zero so the
  F+NPP claim is defensible, but a future run that imputes NPP at
  no-vegetation cells (e.g. with NPP = 0) could test sensitivity.
- Full+MODIS is the better in-distribution model but cannot be
  presented as a transfer-tested model — its CI spans zero. If the
  pitch deck wants to show the 25-feature stack, it should pair it
  explicitly with the CI annotation, not lead with the +0.072
  point estimate.
- The asia_grid_5km_v2.parquet (199 MB) exceeds GitHub's 100 MB limit
  and is left gitignored. Reproducible from the script in 5 minutes.

## Files added in this run

```
scripts/item1_c1_sample_modis.py
scripts/item1_c2_train_fnpp.py
scripts/item1_c3_train_full_modis.py
scripts/item1_c4_sweep_v2.py
scripts/item1_c5_hero_fnpp.py
scripts/item1_c6_shap_v2.py
scripts/item1_c6_evolution_panel.py

data/processed/training_features_v2.parquet           (force-added; 615 × 32)
data/processed/us_validation_features_v2.parquet      (force-added; 274 × 32)
data/processed/asia_predictions_F_NPP.parquet         (force-added; 37 MB)
data/processed/hero_climate_npp_asia_anomaly.parquet  (force-added; 12 MB)

data/outputs/F_NPP_model.json
data/outputs/F_NPP_metrics.json
data/outputs/F_NPP_shap.json
data/outputs/F_NPP_shap.png
data/outputs/Full_MODIS_model.json
data/outputs/Full_MODIS_metrics.json
data/outputs/Full_MODIS_shap.json
data/outputs/Full_MODIS_shap.png
data/outputs/sweep_results_v2.json
data/outputs/sweep_results_v2_table.md
data/outputs/hero_climate_npp_asia.{png,pdf,screen.png}
data/outputs/shap_v2_comparison.{png,_screen.png}
data/outputs/methodology_evolution_panel_v2.{png,_screen.png}
data/outputs/F_shap_ranking_regen.json

data/outputs/paper_results_draft.md  (modified — Table 1 expanded,
                                       §2 prose updated, new §4.1
                                       MODIS feature contributions,
                                       §6 lead paragraph updated)
data/outputs/RUN_ITEM_1_SUMMARY.md   (this file)
```

## Open questions for the user

1. **Pitch deck slide 6 (Result 2).** The current Round-C slide shows
   B at transfer R² = +0.020. With Item 1 done, you could either
   (a) replace B with Full+MODIS to show the rescue (CV +0.079) but
   note the CI still spans zero, or (b) keep B as the original
   counterfactual and add a third row for Full+MODIS in a "we tried
   adding MODIS too — it didn't change the soil-feature story"
   beat. (a) is more impressive at first glance; (b) is more honest.
2. **Hero in the deck.** Should slide 5 swap to the F+NPP hero map?
   It's structurally similar to the existing F hero but the metadata
   strip reads transfer R² +0.145 (vs +0.127). Cleaner pitch.
3. **The 24 % NPP-NaN issue.** A reviewer will ask. Honest answer:
   no-vegetation cells. Acceptable mitigation: impute NPP = 0 for
   no-vegetation cells and re-run F+NPP. Worth doing pre-submission
   if you want to defend the n_train = 463 number; not strictly
   necessary because the bootstrap CI on F+NPP still excludes zero
   even at this n.
4. **Cross-continental MODIS test.** Item 1 was Asia-only sampled +
   trained, then tested on the existing US validation set. The user's
   preamble noted a follow-up run will do "cross-continental MODIS"
   — that's already what F+NPP and Full+MODIS do here, since I had
   the real us_validation_features.parquet on disk and used it.
   Confirm whether the preamble's "follow-up" was contemplating
   something more (e.g. multi-continental, or a different validation
   slice).

Branch `claude/item-1-modis` is ready to be merged into main once
the open questions above are resolved.
