# Task: rebuild the MSHI kilometer-tier pipeline (v3) and run the experiments for the paper

You are working in `Sparkxt-0318/MSHI`, the soil respiration (Rs) upscaling part of the author's project. The author is Siyeong Park. Work as a careful co-author: every number must come from code you have run, and every claim must survive a hostile referee. Don't invent results, data or references. If something can't be verified, mark it `[UNVERIFIED]` and say so.

A handoff bundle comes with this prompt (`handoff/`). Read `handoff/README.md` and `handoff/prep_log.md` in full before you start.

## 1. Where the project stands

An audit (`handoff/prep_log.md`) found that the original pipeline's headline result doesn't hold:

- The website's Asia → US transfer numbers (F +0.127, F+NPP +0.145, Full+MODIS +0.072) reproduce exactly, but only with xgboost 2.1.4.
- The US test set was used for model and feature selection (at least 8 configurations scored on it), so it is no longer a clean test.
- "F+NPP is best" and "soil features hurt transfer" are not significant on a paired, same-site comparison. The clay sign flip disappears on cleaner data.
- `data/processed/training_features.parquet` in the repo is the 3,000-row synthetic demo table, so the Run-A scripts now run on synthetic data.
- The methods page describes a hyperparameter sweep and RF/MLP comparisons that exist nowhere in the repo or its history.

A rebuilt pipeline ("v3", prototype code in `handoff/scripts/`) fixed the data problems. Then:

- **Locked clean test.** A test was pre-registered, then scored once, on Europe. Europe had never been used to score anything. Asia-only selection picked a 2-variable linear model, log Rs ~ MAT + ln(MAP). Europe R² = 0.079 [0.013, 0.125]. This is final and must not be re-selected. See `handoff/ANALYSIS_PLAN_LOCKED.md`.
- **Exploratory transfer results.** The transfer penalty between continents is small. The binding limit is that climate explains little within any continent (R² 0.06–0.45) against a same-site agreement of ICC 0.62–0.82.
- **The new argument the paper will be built on.** Soil respiration is measured in forests but mapped onto landscapes:
  1. 68.5% of plots (SRDB `Ecosystem_type`) are forest, against 30.1% of the MODIS land-cover pixels they sit in. This holds even for coordinates precise to about 10 m.
  2. Given climate, plot type matters for Rs (forest +0.126 log [0.009, 0.244]). Pixel type does not (+0.005 [−0.097, 0.106]), which is attenuation from a mismeasured covariate.
  3. Post-stratifying by vegetation type lowers upscaled totals by 4–15% over the Asia + US MODIS footprint.

  Scaled globally, that is 3–13 Pg C yr⁻¹, the same order as the gap between respiration- and productivity-based budgets (Jian et al. 2022).
- **Closest prior work.** Cao et al. 2026, *Global Change Biology*, doi:10.1111/gcb.70956, reweights sites in "environmental feature space" and finds +6.4 Pg C yr⁻¹ overestimation, mostly in arid zones. Only the abstract is accessible; the feature-space variables are unknown.

The paper must show that our bias is a different mechanism: within climate, within vegetated land, and invisible to gridded covariates.

## 2. Ground rules

1. **Branch, don't overwrite.** Work on a branch `v3-rebuild` and open a PR to `main` at the end. Move superseded outputs and scripts into `legacy/` with a short `legacy/README.md` saying what each was and why it was superseded. Don't delete them.
2. **Reproduce before you extend.** Phase 1 must reproduce the handoff numbers (section 6) within the tolerances given. If something doesn't reproduce, stop and report the difference; don't tune until it matches.
3. **Pre-register confirmatory tests.** Before any confirmatory analysis in Phase 3, write the plan to `analysis_plans/`, commit it, and record the commit hash and SHA-256 in `docs/DECISIONS.md`. Then run. Everything not pre-registered is labelled exploratory in outputs and in the log.
4. **The Europe test is closed.** Never change the model, features or selection rule because of Europe results. Re-running `clean_test` for reproducibility is fine. If a pipeline change moves the Europe numbers, report it as a deviation and keep the locked result as primary.
5. **North America is spent for confirmation.** Use it only for exploratory analyses.
6. **No fabrication.** Every reference you add must be found and checked by DOI on Crossref. If a paper's full text isn't accessible, say what you read.
7. **Keep the biosensor out.** The centimeter-tier biosensor is the subject of a separate manuscript under review. Don't touch `biosensor_samples/`, don't use its data, and exclude it from the paper's data archive manifest. Flag to the author that raw biosensor traces are public in this repo, in case that matters for the other submission.
8. **Don't touch `MSHI-WEB`.** The website is out of scope for now.
9. **Licences.** SRDB and COSORE are MIT. SoilGrids, ESA WorldCover and Esri LULC are CC-BY-4.0. Check WorldClim, MODIS and ESA CCI terms before committing any derived raster. Commit code and small derived tables only; raw downloads go in `data/raw/` (gitignored) and are fetched by the pipeline.
10. **Log everything** in `docs/DECISIONS.md`: each decision, deviation, version and open question, dated. Seed every random step and record package versions in `environment.yml` and a lock file.
11. **Stop at the checkpoints** (end of Phases 1, 2 and 3) and report to the author before continuing.

## 3. Phase 0: housekeeping

- Create branch `v3-rebuild`.
- Restore the real Asia table in place of the synthetic `training_features.parquet`, or move both v1 tables to `legacy/`. Make sure nothing in the new pipeline can read the demo table.
- Add `environment.yml` (Python ≥ 3.11). Pin `xgboost==2.1.4` because the original numbers depend on it. Also add numpy, pandas, scipy, scikit-learn, statsmodels, pyarrow, rasterio, geopandas, pyproj, pystac-client, requests, rdata, matplotlib, pyyaml.
- Copy `handoff/` into `docs/handoff/` so the provenance is in the repo.

## 4. Phase 1: v3 pipeline as a package (reproduce the handoff)

Refactor `handoff/scripts/` into a package `mshi/` with one entry point (`python -m mshi.run --stage all`, plus `make all`). Every version, path and threshold lives in one config, `configs/v3.yaml`.

### Stages and pinned sources

| Stage | Input / source | Notes |
|---|---|---|
| `fetch_srdb` | GitHub `bpbond/srdb`, commit `02163a720bc0b84bd535ad0962c85735816448e8`, `srdb-data.csv` | Verify SHA-256 `c4d7714a0954a0c9b8d4d41ae758defa8c46cb208aa50ef148e762655f892911` |
| `fetch_cosore` | GitHub `bpbond/cosore` v0.8.0, commit `02f32e8e7f9a0f1c26c9dad61c574aef863f1df1` | Large clone (~370 MB); a shallow clone is fine |
| `cosore_annual` | `cosore_aggregate.py` logic | ≥ 150 observation days spanning ≥ 180 calendar days per port; expect 66 sites |
| `build_sites` | `build_sites_v3.py` logic | See filters below |
| `fetch_worldclim` | WorldClim 2.1 bioclim, 2.5′ | `geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_bio.zip` |
| `fetch_soilgrids` | SoilGrids 2.0 WCS, 5–15 cm mean, 0.05° global | 8 variables; unit scaling as in `src/features.py` |
| `modis_points` | Planetary Computer COGs: `modis-17A3HGF-061` (NPP), `modis-11A2-061` (LST day/night) | 2020–2024; 0.05° window mean around each point; NPP valid 0–32,700, × 0.1 → g C m⁻² yr⁻¹; LST > 0, × 0.02 − 273.15 → °C; LST = first 8-day composite of each month |
| `features` | `features_v3.py` logic | Nearest-pixel sampling for gridded rasters |

### Site-build filters

Keep these exactly as in `build_sites_v3.py`:
- 50 ≤ Rs_annual ≤ 4,500 g C m⁻² yr⁻¹.
- Manipulation None, Control or NA.
- Coordinate check: drop an SRDB record if its point is more than 100 km from its reported country, using Natural Earth 1:50m polygons. Excepted territories: Puerto Rico, Greenland, New Caledonia, and Svalbard (reported as Denmark, located in Norway).
- QC: drop alkali/soda-lime methods, Quality_flag Q10–Q14, Annual_coverage < 0.5, Ecosystem_type Wetland/Urban, and records with a Duplicate_record entry.
- Merge records within 5 km by connected components. Target = mean log Rs over the site's records.
- Continent by point-in-polygon, falling back to the nearest polygon within 50 km. Split Russia at 60°E.

Keep a "repo filters only" variant (no QC) for sensitivity.

### Known pitfalls (each cost time in the prototype)

- **SRDB `site_id` indexing.** It must carry the original CSV row index, not the post-filter index.
- **Planetary Computer tokens.**
  - Request the SAS token for the storage container (`/api/sas/v1/token/modiseuwest/modis-061-cogs`), not for the collection; the collection token returns 403.
  - Share one token across threads under a lock, refresh it every few minutes, and force a refresh on any 403.
  - Some STAC items have `datetime = None`; use `start_datetime` instead.
  - About 32 threads is safe.
- **COSORE files.** 24 of 94 datasets fail with the Python `rdata` parser. Record which ones. If R is available, reading them with `readRDS` is an optional improvement, and must be logged as a deviation from the handoff counts.
- **MODIS land cover.** MCD12Q1 is not on Planetary Computer. The repo's GEE export `data/raw/modis/landcover_igbp_2023.tif` covers only the Asia + US + part-of-Oceania footprint.

### Reproduction targets (stop and report if outside tolerance)

| Quantity | Handoff value | Tolerance |
|---|---|---|
| SRDB records after repo filters | 4,771 | exact |
| Records after coordinate check / after QC | 4,781 / 3,694 | ±1% |
| QC removals: method / quality / coverage / ecosystem / duplicate | 450 / 260 / 252 / 243 / 57 | ±2% |
| QC sites by continent: Asia / N America / Europe / S America / Africa / Oceania | 387 / 257 / 236 / 42 / 26 / 23 (total 971) | ±2% |
| Repo-filter sites total | 1,225 | ±2% |
| Locked test: selected model; Asia spatial-CV R²; Europe n; Europe R² and site-bootstrap CI | OLS-TP; 0.143; 235; 0.079 [0.013, 0.125] | same model; ±0.01 R² |
| NPP correlation with the repo's committed NPP at the original 889 sites | r = 0.982 | ±0.01 |

Also add `tests/` with these as regression checks, a smoke test on a 50-site subset, and a check that `clean_test` refuses to run if `ANALYSIS_PLAN_LOCKED.md` doesn't match its recorded hash.

**Checkpoint 1.** Report the reproduction table, any deviations, run times, and anything in the handoff you think is wrong.

## 5. Phase 2: harden the transfer evaluation (exploratory, supporting)

These results support the paper; they are not its headline. Label all of them exploratory.

1. **Continent matrix and leave-one-continent-out.** Learners: OLS-TP; random forest tuned by nested spatial CV within the training continent only; a GAM (pygam or statsmodels splines); and XGBoost with the original fixed parameters. Report R², RMSE in g C m⁻² yr⁻¹, and skill relative to a constant (training-mean) prediction, with spatial-block bootstrap CIs. Continents with fewer than 30 test sites go in a supplementary table only.
2. **Within-continent benchmark with kNNDM CV** (Linnenbrink et al. 2024, doi:10.5194/gmd-17-5897-2024), alongside 5° blocks. If no maintained Python implementation exists, implement it from the paper and test it on a toy case.
3. **Noise ceiling.** Rerun E1 and N3 with a 3-level REML model (site / study within site / record) by continent. Report both ceilings: for a new record from the same study, and for one from an independent study.
4. **AOA sensitivity** (Meyer & Pebesma 2021): DI threshold as the outlier-removed maximum vs the 0.95 quantile; importance weights from permutation vs none. Produce a global DI map at 0.5°.
5. **Why the original US R² was low.** Rerun E4 and E4b cleanly and produce one figure: R² and RMSE for CONUS box vs all of North America.

**Checkpoint 2.** Send a short results table and the figures.

## 6. Phase 3: the new argument, plot vegetation vs mapped landscape (confirmatory core)

### 6.1 Build the inputs

- **Plot vegetation class.** Harmonise SRDB `Ecosystem_type` (plus `Leaf_habit`, `Biome`, `Species` where useful) and COSORE `CSR_IGBP` into: Forest, Grassland, Agriculture, Shrubland, Savanna, Desert, Other. Write the crosswalk to `configs/plot_classes.yaml`, with every SRDB value listed explicitly.
- **Global land cover**, from Planetary Computer (all checked available 2026-11-02):
  - `esa-worldcover`: 10 m, 2020–2021, CC-BY-4.0.
  - `esa-cci-lc`: 300 m, 1992–2020.
  - `io-lulc-annual-v02`: 10 m, 2017–2023, CC-BY-4.0.

  Primary: ESA CCI LC at 300 m. Choose a year near the SRDB median study year and check sensitivity across years. Use WorldCover for the 10-m neighbourhood analyses. Map each land-cover legend to the same seven classes in `configs/landcover_classes.yaml`. State the ambiguous cases explicitly: woody savanna, mosaic classes, tree cover < 40%.
- **Neighbourhood composition at each plot,** from WorldCover: class fractions within 30 m, 100 m, 500 m, 1 km and 5 km buffers.
- **Landscape composition per cell,** on a 0.5° global grid: class fractions from CCI, plus WorldClim climate.

### 6.2 Pre-register before running (Phase 3 confirmatory plan)

The Asia + US pilot (`N2*`) has been seen; the other regions have not. Write and commit `analysis_plans/plot_vs_landscape_v1.md` **before** computing anything for Europe, South America, Africa and Oceania with the new land cover. It must contain:

- **H1, composition mismatch.** In each held-out region, the forest share of plots exceeds the forest share of land in the same climates, defined by k = 500 nearest climate neighbours in standardised (MAT, ln MAP, bio04, bio15) space. Test with a site-bootstrap CI on the difference.
- **H2, attenuation.** In a pooled model log Rs ~ MAT + ln MAP + continent + class, the plot-class forest coefficient exceeds the pixel-class (CCI 300 m) forest coefficient. Test with a bootstrap CI on the difference.
- **H3, upscaling bias.** The climate-only upscaled total over the held-out regions exceeds the post-stratified total, Σ_k f_k · Rs_k(climate). The primary crosswalk and the class pooling (merge any class with fewer than 20 plots into its nearest neighbour, rule fixed in advance) are named in the plan. Report the inflation with a site-bootstrap CI.
- Primary metric, test, data split, crosswalk and pooling rules all fixed. Name sensitivity analyses as such.

Record the plan's hash in `docs/DECISIONS.md`, then run.

### 6.3 Analyses (after the plan is committed)

1. **Confirmatory H1–H3** on the held-out regions. Then report the pooled global estimate as the paper's main number: inflation in % and in Pg C yr⁻¹, with CI.
2. **Falsification checks** (pre-register these too if feasible):
   - Shuffle plot classes within climate strata; the inflation should collapse to about 0.
   - In the climate-only model, residuals at plots should correlate with plot-forest status.
   - Placebo: post-stratify on a random land-cover class assignment, which should give no systematic shift.
3. **Alternative explanations,** each tested and reported:
   - Measurement method and study year confounded with plot type: add both as covariates and restrict to IRGA only.
   - Plot labels reflect study topic, not vegetation: check `Ecosystem_state` and `Species`, and compare against WorldCover at 30 m.
   - Coordinate imprecision: stratify by decimal places in the reported coordinates.
   - Forest plantations inside cropland: use `Ecosystem_state` Managed vs Natural.
4. **Does finer land cover recover the plot signal?** Compare the pixel-type coefficient at 30 m, 100 m, 1 km and 300 m (CCI). Prediction: attenuation shrinks at finer resolution for precisely located plots. Fit a regression-calibration (measurement-error) model and report the corrected coefficient.
5. **Against a Cao-style correction.** Implement an environmental-space representativeness reweighting: inverse local density of sites in standardised (climate + land-cover + NDVI) space, Voronoi-like or kernel density ratio. Show whether the post-stratification bias remains on top of it. This is the key comparison with Cao et al. 2026, whose full text we cannot read. Describe their method only from their abstract and say so.
6. **Small classes.** Fit a hierarchical (partial-pooling) model for class effects, e.g. a mixed model with a class random effect, or Bayesian if time allows. Report how much the Savanna, Shrubland and Desert estimates move.
7. **Link to the Rs–GPP gap** (exploratory, Discussion only). Over the same domain, compare naive and post-stratified Rs with MODIS GPP (`modis-17A2HGF-061`). Report Rs:GPP both ways and compare with the site-level ratio and the global ratios in Jian et al. 2022 (doi:10.1038/s41467-022-29391-5). Don't claim this closes the gap; state what it does and doesn't show.

**Checkpoint 3.** Report H1–H3 with CIs, the falsification results, which alternative explanations survive, and an honest verdict on whether the argument holds. If it doesn't, say so plainly.

## 7. Phase 4: figures and reproducibility

**Figures** come from code (`mshi/figures/`): colour-blind-safe, one style throughout, 300 dpi PNG plus vector PDF.
1. Site map coloured by plot class, with landscape forest share as a basemap.
2. Plot vs pixel vs landscape composition by continent.
3. Plot-type vs pixel-type coefficients at each land-cover resolution (attenuation).
4. Inflation of upscaled totals with CIs, by region and crosswalk.
5. Continent transfer matrix, with within-continent benchmark and noise ceilings.
6. Locked Europe test: predicted vs observed, with RMSE against a constant.

**Reproducibility**
- `README.md` rewritten for v3: what the paper claims, how to run, expected run time, where outputs land.
- `DATA_SOURCES.md` listing every dataset with version, licence, citation and DOI.
- `CITATION.cff`.
- One command reproduces every number and figure from raw downloads, with fixed seeds.
- A results manifest listing each output file's SHA-256.

**Open the PR** with a summary of what changed, what reproduced, what didn't, and open questions for the author.

## 8. Key references (all DOIs checked on Crossref)

**Data**
- SRDB-V5: Jian et al. 2021, *ESSD* 13:255, doi:10.5194/essd-13-255-2021.
- COSORE: Bond-Lamberty et al. 2020, *GCB* 26:7268, doi:10.1111/gcb.15353.

**Rs upscaling**
- Hashimoto et al. 2015, doi:10.5194/bg-12-4121-2015.
- Warner et al. 2019, doi:10.1029/2019GB006264.
- Stell et al. 2021, doi:10.1111/gcb.15666.
- Huang et al. 2020, doi:10.1126/sciadv.abb8508.
- Lu et al. 2021, doi:10.1088/1748-9326/abf526.
- Jian et al. 2018, doi:10.1111/gcb.14301.

**Sampling bias and representativeness**
- Jian et al. 2018 *Earth's Future*, doi:10.1029/2018EF000937.
- Bond-Lamberty et al. 2024 *JGR-B*, doi:10.1029/2023JG007637.
- Cao et al. 2026 *GCB*, doi:10.1111/gcb.70956 (abstract only).
- Diggle, Menezes & Su 2010 *JRSS-C*, doi:10.1111/j.1467-9876.2009.00701.x (preferential sampling).

**Rs–GPP gap**
- Jian et al. 2022, doi:10.1038/s41467-022-29391-5.

**Productivity and vegetation controls on Rs**
- Bahn et al. 2008, doi:10.1007/s10021-008-9198-0.
- Janssens et al. 2001, doi:10.1046/j.1365-2486.2001.00412.x.
- Reichstein et al. 2003, doi:10.1029/2003gb002035.

**Spatial validation**
- Meyer & Pebesma 2021, doi:10.1111/2041-210X.13650.
- Meyer & Pebesma 2022, doi:10.1038/s41467-022-29838-9.
- Ploton et al. 2020, doi:10.1038/s41467-020-18321-y.
- Linnenbrink et al. 2024, doi:10.5194/gmd-17-5897-2024.
- Wadoux et al. 2021, doi:10.1016/j.ecolmodel.2021.109692.

**Flux-tower footprint representativeness (analogue)**
- Chu et al. 2021 *AFM*, doi:10.1016/j.agrformet.2021.108350.
