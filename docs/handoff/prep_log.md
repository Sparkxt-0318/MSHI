# prep_log.md — MSHI-web transfer study, journal preparation

Author: Siyeong Park · Log maintained by Claude (co-author/reviewer role) · Started 2026-11-01

Status: **Checkpoint 1 (reproduction + due diligence 4a–4c).** No manuscript prose written yet. No journal chosen.

---

## 0. Inputs read

| Input | Version read | Notes |
|---|---|---|
| Website mshi-web.vercel.app | live, 2026-11-01 | home + methods page text read; biosensor/about pages checked via source |
| `Sparkxt-0318/MSHI` | HEAD `a809a97` | analysis code, processed tables, outputs |
| `Sparkxt-0318/MSHI-WEB` | HEAD `1dc0b25` | Next.js site source |
| SRDB | GitHub `bpbond/srdb` HEAD `02163a72`, `srdb-data.csv` sha256 `c4d7714a…2911`, fetched 2026-11-01 | repo filters reproduce the draft's 4,771 records exactly, and all 858 SRDB-derived sites match by row index, coordinates and Rs value — so this snapshot is consistent with what the author used `[author to confirm download date]` |
| COSORE | not available | version unknown; `cosore_aggregate.py` input not in repo |
| Colab notebook | not found | none linked from site or repo |

## 1. Reproduction (rule 3.1)

**Environment that reproduces the published numbers exactly:** Python 3.13, xgboost **2.1.4**, numpy 2.5, pandas 3.1, scikit-learn 1.9, default XGBoost seed (0). `requirements.txt` only pins `xgboost>=2.0`; under xgboost 3.4.1 the numbers shift (F 0.149, F+NPP 0.151, Full 0.087). → **Decision:** pin xgboost==2.1.4 and set `random_state` explicitly in the archive.

**Scope limit:** reproduced from the committed processed tables (`training_features_v2.parquet`, `us_validation_features_v2.parquet`), not from raw downloads. Raw SRDB/COSORE, WorldClim and SoilGrids rasters are not in the repo, so `build_target` → `extract` could not be rerun end-to-end. `[OPEN]`

| Config | n_train / n_test | Transfer R² (reproduced) | 95% CI (reproduced) | Website | Match? |
|---|---|---|---|---|---|
| F (8 bioclim) | 600 / 272 | +0.127 | [+0.019, +0.216] | +0.127 [+0.020, **+0.212**] | point yes; **site's upper CI bound is wrong** (repo and reproduction: 0.216) |
| F+NPP (12) | 463 / **223** | +0.145 | [+0.026, +0.241] | +0.145 [+0.026, +0.241], "274 US sites" | numbers yes; **test n is 223, not 274** |
| Full+MODIS (34) | 463 / 223 | +0.072 | [−0.084, +0.189] | +0.072 [−0.084, +0.189] | yes |

Other reproduced facts:
- RMSE / MAE on Rs (g C m⁻² yr⁻¹): F 504 / 359; F+NPP 492 / 343; Full+MODIS 517 / 373; intercept-only (Asia mean) 525 / 376 on the 223-site set.
- Predicted SD of log Rs on US ≈ 0.23 vs observed 0.61: predictions are compressed toward the mean.
- **Seed sensitivity** (20 XGBoost seeds, same data): F 0.115–0.173; F+NPP 0.112–0.165; Full+MODIS 0.071–0.115. The F vs F+NPP ranking flips with the seed.

### 1.1 Same-site, paired comparisons (new)
The site compares F (600/272 sites) with F+NPP (463/223 sites) — different samples **and** different hyperparameters. On the common 463/223 set, with paired bootstrap (2,000 draws):

| Model (common set) | R² | 95% CI |
|---|---|---|
| F, its own params | +0.141 | [+0.033, +0.235] |
| F, F+NPP's params | **+0.159** | [+0.050, +0.245] |
| F+NPP | +0.145 | [+0.026, +0.241] |
| Full+MODIS | +0.072 | [−0.084, +0.189] |
| Intercept-only | −0.002 | — |
| OLS: bio01 + ln(bio12) (2 predictors) | +0.138 | [+0.068, +0.191] |
| OLS: 12 F+NPP features | +0.142 | [+0.067, +0.196] |
| Random forest F+NPP (5 seeds) | +0.145 to +0.164 | — |

| Paired difference | Point | 95% CI |
|---|---|---|
| F+NPP − F | +0.004 | [−0.083, +0.087] |
| Full+MODIS − F+NPP | −0.072 | [−0.176, +0.015] |
| Full+MODIS − F | −0.069 | [−0.190, +0.037] |

**Conclusion:** there is no evidence that NPP improves transfer, and none that soil features significantly reduce it (the direction is consistent but the CIs include 0). A two-variable linear temperature–precipitation model transfers as well as XGBoost. The defensible headline is "all models transfer weakly (R² ≈ 0.14, RMSE ≈ 6% below a constant prediction)", not "F+NPP is best".

## 2. Leakage audit (4b)

| Check | Result |
|---|---|
| Site overlap train/test | None. Regions are disjoint boxes; minimum train–test distance 4,998 km; 0 shared site_ids. ✅ |
| Duplicate records | No exact coordinate duplicates. But dedup snaps to a 0.05° grid and keeps the first record, so close pairs survive: 114 Asia and 47 US sites have a neighbour within 5 km. Within-region only; does not leak across train/test. ⚠️ |
| One record per site | SRDB is record-level. 368 retained Asia cells and 155 US cells had >1 eligible SRDB record (up to 131); one record was kept arbitrarily (sort order), not averaged across years/plots. ⚠️ |
| Gridded features leaking target | None found. NPP/LST/WorldClim/SoilGrids are not derived from Rs. Temporal mismatch noted: SRDB study years 1964–2021 (Asia median 2010, US median 2002); MODIS is a 2020–2024 mean; WorldClim 1970–2000 normals. ⚠️ |
| Preprocessing fitted on test | None. No scaling/imputation; rows with NaN dropped; IGBP one-hot classes chosen from Asia counts only. ✅ |
| **Hyperparameters / model selection using US data** | **Yes — the main problem.** At least 8 feature/hyperparameter configurations (A–F, F+NPP, Full+MODIS) were each scored on the US set, plus Köppen and IGBP subsets, and the best US score is the headline. Config E ("climate + transferring soil") and D ("drop overfit") were defined using cross-region diagnostics that included a model trained on US data (`task5_dual_shap.py`). Hyperparameters are hand-set (depth 3, 200–250 trees) and differ between F and F+NPP. The US set has therefore functioned as a validation set, not an untouched test. ❌ |
| What Asia-only selection would have picked | Within-Asia spatial-CV R² is negative for F (−0.067) and F+NPP (−0.021); Full+MODIS is the only positive one (+0.079). Selection by Asia CV alone would have picked **Full+MODIS**, whose transfer CI spans zero. ❌ |
| Website methods page vs code | Methods page says hyperparameters were swept per CV fold with max_depth 5–7, 400–1,200 trees; RF and MLP were compared; SHAP was computed per held-out fold; blocks are "5° latitude bands". **None of this is in the code**: depth 3, 200–250 trees, no sweep, no RF/MLP script, SHAP on the final model, 5° lat×lon blocks. ❌ |
| Spatial block size | 5° lat×lon blocks, 5 folds. Empirical semivariogram of log Rs in Asia rises to ~sill by 200–300 km; US residuals by ~50–100 km. 5° (~450–550 km) exceeds the range, so the block size is defensible. Justification must be added to the paper. ✅ |
| CI method | Bootstrap of US sites with the model held fixed (2,000 draws). A spatial-block bootstrap gives similar intervals (F+NPP: 1° blocks [+0.020, +0.240]; 2° [+0.037, +0.244]; 5° [+0.024, +0.257]). Training-set and seed uncertainty are not included. ⚠️ |
| src/train.py (not used for headline) | Uses the validation fold as the early-stopping eval set — fold leakage if ever used. ⚠️ |
| Committed v1 table | `data/processed/training_features.parquet` is the 3,000-row **synthetic** demo table, so `task2_sweep.py` and `task2_bootstrap_ci.py` now run on synthetic data. Run-A results (A–E) cannot be reproduced from the repo as committed. ❌ |

## 3. Site selection (4c)

Pipeline (from `src/build_target.py`): SRDB rows with lat/lon and Rs_annual → 50 ≤ Rs_annual ≤ 4,500 g C m⁻² yr⁻¹ → Manipulation is None/Control/NA (4,771 records) + COSORE site-level annual sums (66 sites) → 0.05° grid dedup preferring COSORE (1,393 sites) → bounding boxes: "Asia" 25–180°E, −10–80°N (615); "US" −125 to −66°E, 24–50°N (274); other (504, held aside) → NaN drop per config (F: 600/272; F+NPP: 463/223).

**Not filtered:** measurement method, SRDB Quality_flag, Annual_coverage, Ecosystem_type, Ecosystem_state.

| Composition | Asia box (615) | US box (274) |
|---|---|---|
| Actual location (Natural Earth point-in-polygon) | Asia 534, Europe 65 (incl. all Russia, Estonia 21, Finland 12, Romania 3), Africa 12, Oceania 3 | USA 252, **Canada 21, Mexico 1** |
| Alkali absorption / soda lime method | 64 | 27 |
| Annual_coverage < 0.75 (partial year) | 93 (+54 missing) | 59 (+17 missing) |
| Quality flag Q10/Q11 (potential/suspected problem) | 28 | 13 |
| Wetland / Agriculture (SRDB Ecosystem_type) | 29 / 64 | 12 / 21 |
| Managed ecosystem state | 268 | 74 |
| Coordinate errors found | ≥4 Asia-box sites are longitude-sign errors in SRDB (2 Alberta, Canada; 1 Mexico; 1 "Denmark" site at 55.65°E) — features were sampled at the wrong place | — |

MODIS-missing drops (F+NPP) are not random: in Asia they are concentrated in urban (31/47 dropped), water (24/30) and cropland (28/87) pixels — i.e. many sites fall on MODIS-masked pixels, which also hints at coordinate imprecision. Dropped sites have slightly lower log Rs (Asia 6.49 vs 6.57).

**Representativeness (figure `checkpoint1_sites.png`):** annual T and precipitation overlap broadly; the US set has much lower precipitation seasonality (bio15) than monsoonal Asia; Asia includes tropical sites with no US analogue. 32% of US test sites lie outside the Asian 1st–99th percentile range on at least one F+NPP feature (almost all bio15). F+NPP transfer R² is +0.22 inside the range (n = 151) and +0.01 outside (n = 72) — post hoc, but a strong lead for the area-of-applicability analysis (4e).

**Reverse direction (preview, 4e):** US → Asia transfer R² is −0.087 (F) and −0.056 (F+NPP). Transfer is asymmetric and fails in that direction.

## 4. Novelty (4a)

All references listed in the brief were located and checked by DOI on Crossref. See the table in the checkpoint message. Corrections to the brief:
- "Stell et al. 2021 *Global hotspots…*" does not exist; the real paper is Stell et al. 2021 GCB 27:3923, doi:10.1111/gcb.15666 (spatial bias of SRDB information).
- Tang et al. 2020 is ESSD (Rh), not Biogeosciences; Haaf et al. 2021 is Nature Climate Change (Q10), not Biogeosciences.
- Bond-Lamberty "2018" = Bond-Lamberty, Bailey, Chen, Gough & Vargas 2018, Nature 560:80, doi:10.1038/s41586-018-0358-x.

No paper was found that trains an Rs model on one continent and tests it at sites on another. Warner 2019 and Stell 2021 used non-spatial k-fold CV; Tramontana 2016 (FLUXCOM) used leave-towers-out with post-hoc zone breakdowns. Methods of Hashimoto 2015, Zhao 2017, Huang 2020, Lu 2021, Tang 2020, Yao 2021 and Adachi 2017 were checked from abstracts only. `[OPEN: read full methods before submission]`

**Decision (pending author):** replace "has not been answered in the published literature" with: *"To our knowledge, published global Rs upscaling studies have evaluated models with random or site-level cross-validation, and none has explicitly tested whether a model trained on one continent predicts site-level Rs on another."*

## 5. Website claims contradicted by the repo (for deliverable 8; full list later)

- "transfer R² is highest in Köppen C … collapses toward zero in Köppen D": the repo's Köppen analysis trains a separate model per zone; C = −0.336 [−1.060, +0.035], D = −0.199 [−0.392, −0.061]. Both negative, and Köppen classes are a bioclim heuristic, not the Köppen–Geiger map.
- "Forest biomes transfer reasonably; cropland and grassland transfer worse": repo `igbp_stratification.md` gives forest −0.265 [−0.578, −0.058], cropland −0.143, grassland **+0.275** — the opposite ordering.
- Clay "ρ = +0.302 / −0.048": these are Pearson r from an earlier table. On the current tables: Pearson +0.294 [0.219, 0.368] (n = 594) vs −0.036 [−0.157, 0.084] (n = 272); Spearman +0.280 [0.204, 0.354] vs −0.026 [−0.144, 0.090]. The US value is indistinguishable from zero: "absent in the US", not a sign flip.
- "held-out test on 274 US sites" (F+NPP used 223; and 22 of the 274 lie in Canada/Mexico); "Trained on 615 Asian sites" (about page) vs 463.
- "~5 km grid" / README "1 km": WorldClim inputs are 10 arc-min (~18 km) and SoilGrids 0.1° (~11 km); MODIS 0.05°.
- Biosensor: "calibrated … classifier", "Validated result from the published MSHI dataset", "inoculated soil sample", "the published study" — the linked `paper.pdf` is a GENIUS Olympiad 2026 competition paper, not a peer-reviewed publication. Raw biosensor traces are public in both repos (`biosensor_samples/`, `public/data/biosensor_raw/`). `[OPEN: author to check whether this is compatible with the JES submission; exclude from this paper's archive]`

## 6. Decisions taken

1. Reference environment: xgboost 2.1.4 (exact reproduction).
2. Report RMSE/MAE in g C m⁻² yr⁻¹ and intercept-only + OLS baselines alongside R².
3. Compare feature sets only on a common site set with paired bootstrap.
4. Use spatial-block bootstrap for CIs; add a seed-ensemble interval.

## 7. Open questions for the author

1. COSORE version and the input used by `cosore_aggregate.py`; SRDB download date.
2. MODIS export details (GEE script, collection 6.1?, years 2020–2024 confirmed?, NPP scale factor).
3. WorldClim 10′ and SoilGrids 0.1° — who resampled SoilGrids from 250 m, and how (mean? which version, 2.0)?
4. Any Colab notebook or code not in the repo (RF/MLP comparison, hyperparameter sweep claimed on the methods page)?
5. Which of the US-scored analyses were planned before seeing US results? (Needed for an honest methods statement.)
6. Approve the remedy for test-set reuse (see checkpoint message, option A/B).

---

## 8. Checkpoint 1 → decisions by author (2026-11-01 14:58 local)

- **D5 (author):** go with A + B — reframe as an evaluation paper disclosing reuse of the US set, and add one clean test scored once on untouched sites.
- **D6 (author):** author has no further inputs; provenance to be recovered from the repos.

## 9. Provenance recovered from the repos

| Input | Finding |
|---|---|
| COSORE | v0.8.0, GitHub bpbond/cosore (last commit 02f32e8, 2021-07-16), 94 datasets; `cosore_aggregate.py` reproduces exactly 66 sites (24 RDS unreadable, 1 no qualifying port) |
| SRDB | GitHub HEAD 02163a72 reproduces all 858 sites exactly (see §0) |
| MODIS | GEE collection 061 (`src/download.py`), 2020–2024 means, 0.05°; rasters uploaded by the author 2026-05-07 (commit 2ff82d2); reproduce committed values exactly |
| WorldClim | committed values do not match 10′, 5′ or 2.5′; `src/features.py` points to 30″ → original was most likely 30″ `[UNVERIFIED]` |
| SoilGrids | 2.0, 5–15 cm mean; 0.1° WCS gives r = 0.95–0.99 with committed values but not exact → original resolution unknown `[UNVERIFIED]` |
| RF/MLP comparison, hyperparameter sweep | no code in either repo or its full history (88 commits) → methods-page claims unsupported |

## 10. Pipeline v3 (rebuilt from raw public sources; used for the clean test and experiments)

- **D7:** QC filters, coordinate check (>100 km from reported country), 5-km site merging with site-mean log Rs target, Natural Earth continents (Russia split at 60°E). 971 QC sites: Asia 387, N America 257, Europe 236, S America 42, Africa 26, Oceania 23.
- **D8:** one consistent feature source for every continent: WorldClim 2.1 2.5′; SoilGrids 2.0 0.05° WCS; MODIS C6.1 MOD17A3HGF NPP and MOD11A2 LST (first composite per month) 2020–2024 means over a 0.05° window from Microsoft Planetary Computer (container SAS token). NPP r = 0.982 vs committed; recovers 189 sites lost to masked pixels.
- **D9:** locked analysis plan written and hashed **before** any Europe scoring: `v3/ANALYSIS_PLAN_LOCKED.md`, SHA-256 `9d50e120c42fa8b4ffdac7b98be1cfa461d4c22b7eac7f9a4aaf01e0befe3dac`, 2026-11-01T07:28:35Z. `[OPEN: author should commit this file to a public repo or OSF to give it an external timestamp]`
- Europe was never scored in earlier work (checked: no evaluation against European observations anywhere in the repo).

## 11. Literature review (3 parallel reviews, 30 papers verified by DOI; 22 full text)

Summarised in the Doc "MSHI transfer study — literature review & novelty plan". Key gaps: no region-held-out Rs test; no AOA for Rs; no noise ceiling; no continent-specific slope test; no measurement of how processing choices move validation scores.

## 12. Exploratory experiments (North America already used → exploratory only)

- **E1 noise ceiling:** ICC of log Rs among records within 5 km = 0.75 (605 sites); ceiling R² ≈ 0.75 single record, ≈ 0.84 site mean. Within-site variance mostly plot-to-plot.
- **E2 data hygiene (Asia→NA, C8 XGB):** repo filters 0.31 [0.22, 0.39]; QC 0.36 [0.25, 0.45]; soil lowers, NPP ≈ no change.
- **E3 shift:** adversarial AUC 0.98 (bio15, bio12); Asia-trained 0.367 vs NA-trained spatial CV 0.375 → no detectable concept shift; importance weighting hurts (0.297, ESS 28); slopes equal across continents except NPP (p = 0.02).
- **E4 ablation:** site-mean vs single-record target: no change. Test region drives R²: CONUS box 0.13 (RMSE 0.56); NA outside box 0.51 (RMSE 0.66); all NA 0.31. **R² is not comparable across transfer tests → always report RMSE + skill vs constant.**
- **E5 global AOA (C8):** all-site model 87.3 Pg C/yr; 10% of land / 6% of flux outside AOA (Arctic 24%, tropics 17% of area). Asia-only model: 27.5% of land / 20% of flux outside.
- Clay: v3 marginal r Asia +0.30 (n 383), NA +0.13 (n 257); no sign flip; no conditional effect.

## 13. Locked clean test — Asia → Europe (scored once, 2026-11-01 ~08:25 UTC)

- Plan SHA-256 9d50e120…3dac (locked 07:28:35Z). Results file `v3/exp/clean_test_europe.json`, SHA-256 b091795f9127d1de873ce42290b391d3d006775c9404ff36f0cb79671256d1e6.
- **Selection (Asia only):** OLS-TP (log Rs ~ bio01 + ln bio12) had the highest spatial-CV R² (0.143 ± 0.076) of 11 candidates; best ML was RF C8+MODIS 0.132; all XGB ≤ 0.046.
- **Europe (n = 235):** R² = 0.079, site-bootstrap 95% CI [0.013, 0.125]; 2° block-bootstrap CI [−0.000, 0.134]. RMSE 385.5 vs 386.9 g C m⁻² yr⁻¹ for the constant Asia mean; skill in log space 5.9%; Spearman 0.26; bias −0.046 log.
- **H1:** met on the site bootstrap, borderline on the spatial bootstrap; no practical gain in g C units.
- **H2:** not testable — 233/235 Europe sites inside the AOA of the 2-predictor model.
- Secondary (all candidates on Europe, no re-selection): every ML model's CI includes 0 (range −0.051 to +0.074).
- Deviation from plan: none. (Seed range not applicable to OLS.)

## 14. E6 continent matrix (exploratory, after the locked test)

- OLS-TP: within-continent spatial CV R² — Asia 0.163, Europe 0.058, N America 0.451. Leave-one-continent-out — Asia 0.125, Europe 0.088, N America 0.363. Asia→Europe 0.079, Asia→N America 0.348.
- XGB C8: Asia→Europe −0.053, within-Europe CV −0.157, within-Asia −0.001, within-NA 0.375.
- **Reading:** the transfer penalty (within-continent minus cross-continent) is small (≤ 0.09 R²) and zero for Europe; the binding limit is that climate explains little within a continent (Europe ≈ 0.06), far below the noise ceiling (ICC 0.62–0.82). The simple linear model transfers better than XGB nearly everywhere.
- Sensitivity (repo filters, plan-specified): selected OLS-TP again; Europe n = 282, R² 0.052 [0.004, 0.092] (block [−0.004, 0.099]); RMSE 405.1 vs 405.9 intercept.

## 15. Author asked for a genuinely new argument (2026-11-01 19:18 local) — pilots

- **N1 greener-than-peers sites:** median NPP rank among 500 climate peers 0.53 [0.49, 0.60] Asia, 0.57 [0.52, 0.65] NA; site/peer NPP 1.015–1.017; climate-only inflation 1.6–3.0% → small, dropped as headline.
- **N2 plot–pixel mismatch (headline candidate):** plots 68.5% forest vs their MCD12Q1 pixels 30.1% vs landscape in same climates 17–32%. Holds at ≥4-decimal coordinates (34% of forest plots in forest pixels) → not coordinate error. Given climate: plot-forest +0.126 log [0.009, 0.244]; pixel-forest +0.005 [−0.097, 0.106] (attenuation). Post-stratified totals over Asia+US footprint: binary +4.3% [0.3, 8.8]; 6-class +7.5% [3.1, 11.4] (woody savanna→forest) to +14.6% [7.8, 21.4] (→savanna); deserts excluded +7.2% [3.7, 10.4] / +15.0% [8.9, 22.0]. Fragile classes: savanna 5–12 plots, shrub 14–31, desert 13.
- **N3 reproducibility:** different-study pairs at same site semivariance 0.136 vs same-study 0.073 (QC); variance shares site 68% / study 16% / record 16%.
- **N4 Rs/NPP ratio target:** worse transfer everywhere → dropped.
- **Novelty check:** closest prior = Cao et al. 2026 GCB 10.1111/gcb.70956 (environmental-space unevenness → +6.4 Pg, arid-dominated) `[UNVERIFIED full text — abstract only]`. Within-climate vegetation-composition mismatch + land-cover attenuation + post-stratification: not found.
- Files: v3/exp/N1_selection_bias.json, N2_plot_pixel.json, N2b_forest_bias.json, N2c_poststrat.json, N2d_poststrat_no_desert.json, N3_reproducibility.json.
