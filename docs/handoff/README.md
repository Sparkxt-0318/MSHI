# Handoff bundle: MSHI v3 audit and pilots (2026-11-01 to 02)

This is the starting material for the rebuild in `PROMPT_mshi_v3.md`. Treat everything here as **prototype code**: it ran and produced the numbers below, but it uses hard-coded paths, has no tests, and was written fast. Refactor it; don't copy it in as-is.

## Contents

| Path | What it is |
|---|---|
| `prep_log.md` | Decision log from the audit. Every check, number and open question, in order. |
| `ANALYSIS_PLAN_LOCKED.md` + `.sha256` | Pre-registered Asia → Europe test, locked 2026-11-01T07:28:35Z, SHA-256 `9d50e120…3dac`. **Already scored. Do not edit.** |
| `build_summary.json` | Record counts from the v3 site build. |
| `checkpoint1/` | Audit of the original pipeline: reproduction, leakage and site-selection checks, site figure. |
| `results/` | One JSON per analysis (see the table below). |
| `scripts/` | The code that produced every file in `results/`. |

## Scripts, in pipeline order

| Script | Role | Notes |
|---|---|---|
| `cosore_aggregate.py` | COSORE v0.8.0 → site annual Rs | Copy of the repo's own script with local paths. Yields 66 sites; 24 RDS files can't be read by `rdata`. |
| `build_sites_v3.py` | SRDB + COSORE → QC'd records → 5-km sites → continents | Args: `SRDB_CSV COSORE_CSV NATURAL_EARTH_DIR OUT_DIR` |
| `get_soilgrids05.py` | SoilGrids 2.0 5–15 cm mean, global, 0.05°, via WCS | |
| `modis_points_lst.py` | MODIS C6.1 NPP (`--npp-only`) / LST (`--lst-only`) window means at points, from Planetary Computer | See the Planetary Computer pitfalls in the prompt. LST takes about 45 min for 1,530 points. |
| `features_v3.py` | Attach WorldClim 2.1 2.5′, SoilGrids, MODIS to sites | |
| `clean_test.py` | Locked Asia-only selection + single Europe score + AOA | The primary result. Ran under xgboost 2.1.4. |
| `exp_*.py` | Exploratory experiments E1–E6, N1–N3 | E2/E3/E4/E6-XGB ran under xgboost 3.4.1; OLS results don't depend on the version. |
| `reproduce.py`, `audit.py`, `srdb_audit.py`, `site_figure.py`, `validate_features.py` | Checkpoint-1 audit of the original pipeline | Run against the original committed tables. |

## Results index

| File | Question | Headline |
|---|---|---|
| `clean_test_europe.json` | Locked test | OLS T+lnP selected; Europe R² 0.079 [0.013, 0.125], n = 235; RMSE 385.5 vs 386.9 g C m⁻² yr⁻¹ for a constant |
| `clean_test_europe_repo_sensitivity.json` | Same with repo filters only | R² 0.052 [0.004, 0.092], n = 282 |
| `E1_noise_ceiling.json` | Same-site agreement | ICC 0.75 overall (Asia 0.73, NA 0.82, Europe 0.62) |
| `E2_E3_shift.json` | Data hygiene; covariate vs concept shift | Asia→NA 0.36 (QC); adversarial AUC 0.98; Asia-trained 0.367 vs NA-trained 0.375 |
| `E4_ablation.json`, `E4b_regions.json` | Why the original transfer R² was low | Test-region definition: CONUS box 0.13 vs all NA 0.31 |
| `E5_global_aoa.json` | Area of applicability | 10% of land / 6% of flux outside (all sites); 27.5% / 20% (Asia only) |
| `E6_matrix_*.json` | Continent transfer matrix | Transfer penalty ≤ 0.09 R²; within-Europe R² 0.06 |
| `N1_selection_bias.json` | Are sites greener than their climate peers? | Barely: +1.5% NPP; 2–3% inflation |
| `N2_plot_pixel.json`, `N2b_forest_bias.json` | Plot vs pixel vegetation | 68.5% of plots are forest vs 30.1% of their pixels; plot coefficient +0.126 vs pixel +0.005 |
| `N2c_poststrat.json`, `N2d_poststrat_no_desert.json` | Post-stratified totals | +4.3% to +15.0% inflation of naive totals, depending on crosswalk |
| `N3_reproducibility.json` | Do independent studies at a site agree? | Between-study semivariance 0.136 vs within-study 0.073 |
