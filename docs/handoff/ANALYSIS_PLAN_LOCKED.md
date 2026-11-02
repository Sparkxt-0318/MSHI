# Locked analysis plan — clean cross-continental test (Asia → Europe)

Locked: 2026-11-01, before any model trained on Asia has been scored on any European site.
The SHA-256 of this file is recorded in prep_log.md. Any deviation is reported as a deviation.

## Why
The North America (NA) test set was used for model and feature selection in earlier work. Europe has never been
used to score any model (checked: no evaluation against European observations exists in Sparkxt-0318/MSHI).

## Data (pipeline v3, rebuilt from raw sources)
- Records: SRDB v5 (GitHub bpbond/srdb HEAD 02163a72) with the repo filters (50 ≤ Rs_annual ≤ 4500; Manipulation
  None/Control/NA) + COSORE v0.8.0 site annual sums (66 sites; scripts/cosore_aggregate.py).
- Coordinate check: drop SRDB records whose point lies > 100 km from the reported country (territories excepted).
- QC filters (primary analysis): drop alkali-absorption/soda-lime methods, Quality_flag Q10–Q14, Annual_coverage < 0.5,
  Ecosystem_type Wetland/Urban, records with a Duplicate_record entry.
- Sites: records within 5 km merged (connected components); target = mean log(Rs_annual) over a site's records.
- Continent: Natural Earth 1:50m point-in-polygon (nearest within 50 km); Russia split at 60°E.
- Train = Asia sites; Test = Europe sites. Sensitivity: same analysis with repo filters only (no QC).
- Features (sampled at site, nearest pixel unless stated): WorldClim 2.1 2.5′ bio01–bio19; SoilGrids 2.0 5–15 cm mean
  at 0.05° (soc, nitrogen, phh2o, clay, sand, silt, bdod, cec); MODIS C6.1 MOD17A3HGF NPP 2020–2024 mean and MOD11A2 LST
  day/night 2020–2024 (first composite of each month) as means over a 0.05° window (Planetary Computer COGs).

## Candidate set (fixed now)
Predictor sets:
- C8 = bio01, bio04, bio05, bio06, bio12, bio14, bio15, bio17
- C8+NPP = C8 + npp
- C8+MODIS = C8 + npp, lst_day, lst_night, lst_diurnal_range   (analogue of the earlier "F+NPP")
- C8+SOIL = C8 + 8 SoilGrids variables
- ALL = C8 + SOIL + MODIS
Learners:
- XGB: n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
  reg_alpha=0.5, reg_lambda=2.0, random_state=0 (the earlier F+NPP settings; not tuned further)
- RF: 500 trees, min_samples_leaf=5, max_features=0.5, random_state=0
- OLS-TP: log Rs ~ bio01 + ln(bio12) (fixed simple baseline; always reported, also selectable)
Rows with any missing predictor in a given set are dropped for that set.

## Selection rule (Asia only)
Mean R² over 5-fold spatial-block CV within Asia (5° × 5° blocks), repeated with 3 block-to-fold seeds (42, 43, 44).
Pick the highest mean CV R²; if another candidate is within 0.01 and has fewer predictors, pick the simpler one.
The selected model is refit on all Asia sites (its own complete rows) and scored once on Europe.

## Primary outcome and tests
- Primary metric: Europe R² = 1 − SSE/SST of log Rs (SST around the Europe mean), with 95% CI from a 2,000-draw site
  bootstrap and from a 2° spatial-block bootstrap. RMSE and MAE in g C m⁻² yr⁻¹; intercept-only (Asia mean) baseline.
- H1: selected model has Europe R² > 0 (95% site-bootstrap CI lower bound > 0).
- H2: Area of applicability (Meyer & Pebesma 2021): DI computed in the selected model's standardised predictor space
  (importance-weighted for tree models using mean |SHAP|/permutation importance; unweighted for OLS), threshold =
  upper whisker (Q3 + 1.5·IQR) of the cross-validated training DI from the Asia spatial-block folds. Prediction:
  R² inside AOA > R² outside AOA (difference reported with bootstrap CI).
- Every candidate is also reported on Europe (secondary, labelled as such; no re-selection on Europe).
- Seed spread: selected learner refit with seeds 0–19; report range of Europe R².

## What happens after
Only after this test is scored: exploratory analyses (continent transfer matrix, noise ceiling, covariate-vs-concept
shift, data-quality stratification) are run and labelled exploratory.
