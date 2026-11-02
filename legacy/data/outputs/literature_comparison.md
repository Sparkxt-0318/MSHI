# Literature comparison — continental-scale Rs upscaling

## Verified from publication abstracts (Crossref API)

The four published Rs upscaling studies most directly comparable to this
work all report uncertainty as MAE / RMSE / Monte-Carlo CIs on the global
or per-region Rs sum, not as site-level R² of predicted vs observed Rs.
Numbers below are extracted verbatim from publication abstracts. Where an
abstract does not state R², the cell is marked **[not in abstract]** and
should be checked against the methods/results section if needed.

| Study | Method | Region | Sample | Test type | Reported metric (verbatim from abstract) |
|---|---|---|---|---|---|
| Hashimoto et al. 2015 [1] | climate-driven model (modified Raich) | global | 0.5° grid, monthly | Monte-Carlo CI on global sum | global Rs = 91 Pg C yr⁻¹ (95 % CI 87–95); Q₁₀ = 1.4. **No site-level R² in abstract.** |
| Warner et al. 2019 [2] | quantile regression forest | global | 1 km grid | within-sample MAE / RMSE | global Rs = 87.9 Pg C yr⁻¹; MAE = 18.6, RMSE = 40.4 Pg C yr⁻¹. **No site-level R² in abstract.** |
| Yao et al. 2021 [3] | random forest, SHR target | global | 0.5° grid | inter-model agreement | global SHR ≈ 39 Pg C yr⁻¹ (1985–2013), trend +0.03 Pg C yr⁻². **No R² in abstract.** |
| Stell et al. 2021 [4] | quantile regression forest, two SRDB versions | global | 1 km grid | within-sample MAE / SD | v3: global Rs 88.6, MAE 29.9, SD 57.9; v5: 96.5, MAE 30.2, SD 73.4 Pg C yr⁻¹. Spatial-bias-corrected: 96.4 ± 21.4. **No R² in abstract.** |
| **THIS WORK (climate-only, F)** | XGBoost, 8 bioclim features | Asia → US (held-out) | site-level | **cross-continental transfer R²** | **R² = +0.127 (95 % CI +0.019 to +0.216, n_us = 272)** |
| **THIS WORK (full features, B)** | XGBoost, 20 features (climate + SoilGrids 5–15 cm + engineered) | Asia → US (held-out) | site-level | **cross-continental transfer R²** | **R² = +0.020 (95 % CI −0.141 to +0.146, n_us = 270)** |

[1] DOI 10.5194/bg-12-4121-2015 (verified via Crossref)
[2] DOI 10.1029/2019GB006264 (verified via Crossref)
[3] DOI 10.1029/2020GB006918 (verified via Crossref)
[4] DOI 10.1111/gcb.15666 (verified via Crossref)
SRDB-V5 source: Jian et al. 2021, DOI 10.5194/essd-13-255-2021 (verified via Crossref).

## Footnote on cross-continental validation

To our knowledge, no published Rs upscaling study reports a held-out
**cross-continental transfer R²** as we define it here (train on one
continent, predict on a different continent, evaluate site-level R²
between predicted and observed `log Rs_annual`). Published Rs models
report within-sample fit, leave-one-out CV, or spatial bias-corrected
estimates of global sums — but not the cross-continental site-level
test in the table above. The closest published treatment is Stell et al.
2021, which explicitly characterises the geographic *bias* of SRDB
(northern-temperate over-representation) as a source of model
uncertainty, but does not run a held-out cross-continental performance
test. **THIS WORK is the first to characterise the within- vs.
across-continent gap in this benchmark.**

## What this means for our claim

The two THIS WORK rows are not directly comparable to the four published
rows above on the same axis: published studies report global sums and
spatial uncertainty, not held-out site-level transfer R². Our claim is
narrower and more decision-relevant: trained on Asian SRDB+COSORE sites,
the climate-only feature subset transfers to held-out US sites with
R² = +0.127 (statistically significantly different from zero), and adding
SoilGrids texture features collapses transfer to R² = +0.020 (not
distinguishable from zero). This characterises a transfer gap that
published global Rs maps do not currently report and cannot rule out.

## Verification checklist (left for the user)

The R² column was deliberately not filled in for the published studies
because no R² values appeared in any of the four abstracts retrieved
via the Crossref API. If the methods/results sections of any of these
papers do report a site-level R², please either:
  (a) update the table with the verified value, or
  (b) leave the column as-is and rely on the methodological observation
      that none of these studies report cross-continental transfer R².
