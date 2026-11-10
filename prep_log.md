# MSHI soil-respiration transfer paper: preparation log

This file did not exist in the repository working folder when the 2026-11-10 session started, and
`audit_scripts.zip` was not present either (searched the whole container and every remote branch of
Sparkxt-0318/MSHI). The previous audit's findings are therefore known only from the task brief; they
are quoted below as "audit (brief)" and were not re-run unless a section says so. Scripts from this
session are in `audit/`, numbered from 20.

---

## 2026-11-10: three candidate contributions (transfer matrix, noise ceiling, SRDB coordinate errors)

Scope: Step 0 (clean global site table), Analysis 1 (continent transfer matrix), Analysis 2 (ceiling
on explainable variance), Analysis 3 (SRDB coordinate/metadata errors), novelty checks, figures.
No manuscript prose and no journal choice, as instructed. The electrochemical biosensor data in
`biosensor_samples/` was not opened or used.

### Setup and provenance

- Branch `claude/mshi-soil-respiration-candidates-5vh174`, starting from main @a809a97.
- Network: the shared Default cloud environment blocked WorldClim (`geodata.ucdavis.edu`), Crossref
  (`api.crossref.org`; `doi.org` content negotiation redirects there), ESSD, OSTI, Europe PMC and
  OpenAlex (proxy 403 on CONNECT). With the author's approval a personal cloud environment "MSHI"
  was created with exactly these hosts: github.com, raw.githubusercontent.com, doi.org,
  geodata.ucdavis.edu, api.crossref.org, essd.copernicus.org, www.osti.gov, api.openalex.org,
  www.ebi.ac.uk, pmc.ncbi.nlm.nih.gov, eutils.ncbi.nlm.nih.gov. OpenAlex then refused keyless
  requests (shared-IP quota exhausted); getting a key requires sending an email address, which was
  not done, so OpenAlex was not used. Publisher hosts (Wiley, Elsevier, Springer, IOP, nature.com,
  AGU, MDPI, other Copernicus journals) stayed blocked.
- Python 3.11.15 virtual environment (`/home/user/venv-mshi`, outside the repo). Pinned:
  xgboost 2.0.3 (the version with which the audit reproduced the published transfer R2 values),
  numpy 1.26.4, pandas 2.2.3, scipy 1.13.1, scikit-learn 1.5.2, statsmodels 0.14.4, geopandas
  1.0.1, shapely 2.0.6, pyproj 3.7.0, pyogrio 0.10.0, rasterio 1.4.3 (GDAL 3.9.3), pyarrow 17.0.0,
  matplotlib 3.9.2, joblib 1.4.2, remotezip 0.12.3, rdata 0.11.2, tifffile 2024.8.30, imagecodecs
  2024.6.1. Each output JSON records the versions it ran with.
- Seeds: 42 for every bootstrap and fold assignment; XGBoost seeds 42-61 (20 fits per model).

| Input | Version / hash | Notes |
|---|---|---|
| SRDB | git 02163a7 (data update 30 Dec 2025); srdb-data.csv sha256 c4d7714a0954a0c9... | 14,169 records; srdb-studies.csv is Mac Roman with CR line endings |
| COSORE | git 02f32e8, DESCRIPTION Version 0.8.0 (no `v0.8.0` git tag exists; latest tag v0.7) | 94 dataset folders (3 TEST) |
| WorldClim 2.1 30" bio 1,4,5,6,12,14,15,17 | from wc2.1_30s_bio.zip via remotezip (8 of 19 members, 4.5 GB); CRC-32 checked; sha256 in data/raw/worldclim30s/MANIFEST.json | fetched 2026-11-10 06:55-06:57 UTC |
| Natural Earth 1:10m admin-0 map units, admin-1, land | github.com/nvkelso/natural-earth-vector @ca96624 (5.2.0-pre); map units sha256 57da82be755f4afc... | naciscdn.org blocked; GitHub mirror used |
| MODIS NPP 2020-2024 mean | data/raw/modis/npp_2020_2024_mean.tif sha256 df6c3caf8e04bc31... | float64, predictor 2: GDAL 3.9.3 cannot decode it; read with tifffile; origin -125.0006, 87.8193 (off the 0.05 grid by ~0.39 px, so sampled with its own geotransform) |

### Decisions

1. **Log and scripts.** No earlier log or audit scripts were available, so this log starts here and
   scripts are numbered 20-34. `audit/mshi_common.py` and `audit/mshi_sites.py` hold shared code.
2. **SRDB reading.** `keep_default_na=False, na_values=[""]`, so the string "None" survives;
   unmanipulated = `Manipulation == "None"` or missing.
3. **Quality flags.** Parsed into sets after normalising spellings ("Q1" -> Q01, "Q01, Q03",
   "Q03,Q10,Q16"); a record is dropped if any flag is in Q10-Q14. Q15 (seasonal model, not annual)
   and Q16 (soil-water model) are not in the brief's list and were kept (open question 1).
4. **Known duplicates (added rule).** Records with `Duplicate_record` set are dropped (13 after the
   earlier rules; 64 among records with Rs_annual). Reason: duplicated values would shrink the
   within-cell variance in Analysis 2. Exact-equal values across studies in the same cell were also
   counted (17 pairs, strict) and tested as a sensitivity (no change).
5. **Annual coverage.** Records with coverage < 1 are dropped. Records with coverage missing (368
   SRDB records) are kept in variant `incl_missing` and dropped in variant `strict`. Every analysis
   was run on both; `strict` is primary in figures and text.
6. **Continents.** Natural Earth map units (which split French Guiana, Réunion, Puerto Rico, etc.
   from their parent countries), CONTINENT field, with UN subregions Central America + Caribbean +
   South America grouped as "South & Central America" (so Mexico is in it). Overrides: Russia east
   of 60 E -> Asia (Ural split; NE puts all of Russia in Europe), Hawaii -> Oceania, Canary Islands
   -> Africa. Points within 10 km of a land unit take that unit (coastal sites). No cell had records
   in two continents.
7. **Country check tolerance.** A record agrees with its Country field if its point is inside, or
   within 10 km of, any map unit carrying that name (also matching sovereign names, so "Denmark" in
   Greenland agrees). 10 km covers 1:10m generalisation and coordinate rounding. Every disagreement
   beyond 10 km is flagged and excluded from modelling, including the low-severity near-border and
   near-offshore classes (open question 3).
8. **Cells.** MODIS-CMG-aligned 0.05-degree cells (floor binning from 180 W / 90 N), unlike
   `src/build_target.py`, which used round() and kept one arbitrary record. Site value = mean of
   log Rs over all records in the cell; `n_records`, `sd_log_rs`, `n_studies` are kept.
9. **WorldClim sampling.** Nearest 30" pixel at each record location; if nodata, the nearest valid
   pixel within 3 pixels (~2.7 km) (12 records); 8 records with no value within 3 px were dropped.
   Site predictors = mean over the unique record locations in the cell.
10. **COSORE annualisation (rewritten).** Only ports with `CSR_MSMT_VAR == "Rs"` and
    `CSR_TREATMENT == "None"` (the old `scripts/cosore_aggregate.py` also averaged trenched,
    girdled, warmed and irrigated ports and NEE/Reco chambers). One record per dataset x calendar
    year; a port-year counts only if all 12 months have >= 5 days of data (the analogue of SRDB
    annual coverage = 1); fluxes outside [-2, 50] umol m-2 s-1 dropped; annual Rs = day-weighted
    mean of monthly means x 12.011 x seconds / 1e6. With rdata 0.11.2, 85 of 91 datasets read;
    the 6 failures have no `data.RDS` in the repository (not a parse error, unlike the 24 failures
    noted last time). Result: 63 dataset-years from 28 datasets. Requiring only >= 1 day per month
    would add one dataset (29).
11. **Analysis 1 design.** Train continents need >= 150 sites; test continents >= 20 sites.
    XGBoost grid: max_depth {1,2,3,4,6} x learning_rate {0.03,0.1} x min_child_weight {1,5,10} x
    reg_lambda {1,10}, subsample = colsample = 0.8, n_estimators {50,100,150,300,600} read off one
    600-tree fit with `iteration_range`. The first grid (depth >= 2, >= 150 trees) put the optimum
    on its edge, so it was widened before any result was recorded. Selection: lowest pooled
    out-of-fold MSE under 5-fold 5-degree spatial-block CV inside the training continent. The test
    continent never enters tuning. Within-continent skill: 5-fold 5-degree block CV with the whole
    tuning repeated inside each outer training set (nested). R2 on log Rs with test-set SST; RMSE,
    MAE and bias in g C m-2 yr-1 after exp() (no smearing correction); Spearman on any scale.
12. **Analysis 2 noise model.** The brief's one-way decomposition was run, but records in the same
    cell and same study agree twice as well as records from different studies (half squared
    difference 0.07 vs 0.17), and most cells hold one study. The primary ceiling (B2) therefore uses
    a nested cell -> study -> record model. The one-way pooled ceiling (B1) is reported as an
    optimistic upper value. A semivariogram-based ceiling (B3) uses the 0-10 km semivariance.
    Exponential variogram fits are restricted to lags <= 1600 km: fits to all lags ran to the range
    bound because the continental-scale trend makes the field non-stationary.
13. **Analysis 3 classification.** Order: Region names the admin-1 unit the point is in ->
    country label wrong; sign flip or lat/lon swap lands in the stated country -> coordinate fix;
    point at sea; near border; title/Region text names the actual country -> label wrong; Region
    names a province of the stated country -> coordinates wrong; else unclear. Same-site rule:
    if other records of the same study and site name lie in the stated country and agree within
    0.1 deg, their coordinates are the proposed fix. Species names containing countries ("Norway
    spruce", "Turkey oak") are stripped before text matching. "Corrected" policy = high- and
    medium-confidence fixes applied, rest excluded.
14. **XGBoost tuning instability (found while running Analysis 3).** Re-tuning on data sets that
    differ by a handful of sites can change the selected configuration (e.g. North America:
    depth 4 / 100 trees -> depth 6 / 50 trees) and move transfer R2 by up to 0.17. Analysis 3
    therefore also reports XGBoost with hyperparameters fixed at the `excluded` values, and
    `31_a1_tuning_sensitivity.py` reports transfer R2 across the 10 best configurations.
15. **Figures.** Reference palette slots 1-3 (blue, orange, aqua), validated with the dataviz
    validator on white for all pairs (worst CVD dE 9.2; aqua < 3:1 contrast so every series has a
    legend/label). The same colour always means the same training continent. R2 heat maps use a
    diverging blue-grey-red ramp with matched OKLab lightness per arm, saturating at +-0.5 (cell
    text gives the real value).

### Step 0 results (`audit/outputs/step0_summary.md`, `step0_counts.json`)

SRDB rules applied in order (records removed): Rs_annual reported 14,169 -> 7,792 (-6,377);
unmanipulated -> 4,964 (-2,828); coordinates -> 4,830 (-134); 50-4,500 -> 4,770 (-60); no Q10-Q14
-> 4,508 (-262); not a known duplicate -> 4,495 (-13); coverage >= 1 or missing -> 3,614 (-881);
country agrees with coordinates -> 3,533 (-81). COSORE: 63 records, none removed. Combined: 3,596,
of which 8 lacked WorldClim -> 3,588 records (incl_missing), 3,220 records (strict).

Marginal counts among the 7,792 records with Rs_annual (each rule alone): manipulated 2,828; no or
invalid coordinates 162; outside 50-4,500 72; Q10-Q14 318; known duplicate 64; coverage < 1 1,482;
coverage missing 613; country/coordinate mismatch 149.

| Variant | Records | Sites | AS | NA | EU | SCA | AF | OC | Cells with > 1 record |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| strict | 3,220 | 965 | 392 | 210 | 226 | 77 | 27 | 33 | 60.5% |
| incl_missing | 3,588 | 1,061 | 432 | 236 | 243 | 84 | 31 | 35 | 59.6% |

The brief's rough counts (Asia ~538, North America 342, Europe 321, SCA 93, Africa 43, Oceania 39)
were higher because they predate the coverage, quality-flag, duplicate and country rules.
Training continents: Asia, North America, Europe. Test-only: SCA, Africa, Oceania. 576 strict sites
(639 incl_missing) have a MODIS NPP value.

### Analysis 1 results (`audit/outputs/a1/`, full tables in `audit/outputs/tables.md`)

R2 (95% bootstrap interval), strict / incl_missing:

| Pair | OLS log P | XGBoost (20 seeds) |
|---|---|---|
| AS -> NA | 0.202 [0.114, 0.268] / 0.256 [0.166, 0.324] | 0.210 [0.102, 0.300] / 0.289 [0.186, 0.372] |
| NA -> AS | 0.034 [-0.134, 0.172] / 0.005 [-0.167, 0.157] | -0.042 [-0.185, 0.071] / 0.059 [-0.074, 0.170] |
| AS -> EU | -0.001 [-0.064, 0.051] / -0.003 | -0.134 [-0.265, -0.018] / -0.073 |
| EU -> AS | 0.081 [-0.001, 0.144] / 0.086 | -0.166 [-0.313, -0.053] / -0.106 |
| NA -> EU | -0.041 / -0.074 | -0.083 / -0.066 |
| EU -> NA | 0.115 [0.023, 0.177] / 0.130 | -0.089 / 0.051 |
| AS -> AF (27/31 sites) | 0.143 / 0.181 | 0.418 [-0.045, 0.611] / 0.303 [0.063, 0.538] |
| AS -> SCA | 0.022 / 0.020 | 0.159 [-0.376, 0.424] / 0.100 |
| any -> OC | -0.10 to -0.64 | -0.08 to -0.53 |
| within AS (block CV) | 0.126 / 0.143 | 0.213 [0.113, 0.299] / 0.184 |
| within NA (block CV) | 0.211 / 0.297 | 0.249 [0.148, 0.332] / 0.297 |
| within EU (block CV) | -0.045 / -0.010 | -0.139 [-0.235, -0.068] / -0.065 |
| within SCA (block CV) | -0.013 / 0.108 | 0.479 [0.235, 0.665] / 0.155 |

- Asia -> North America is the only cross-continent pair with a clearly positive interval in both
  variants; its reverse is about zero. Europe has no skill as source, target, or within itself.
- XGBoost does not beat OLS on log precipitation for AS -> NA: difference +0.008 [-0.060, 0.063]
  (strict), +0.033 [-0.012, 0.081] (incl_missing). OLS on MAT + log P adds +0.007 [-0.031, 0.046].
- Coverage (15 pairs, descriptive only): Asia's training climate covers 98% of North American sites
  inside its area of applicability; North America covers 46% of Asian sites; Europe covers 1-36%
  of any continent. Spearman rho between XGBoost R2 and mean dissimilarity index -0.87 (strict),
  -0.76 (incl_missing); rho with the share of test sites inside the AOA +0.61 / +0.53. OLS skill
  tracks coverage weakly (rho -0.50 / -0.44 with mean DI). Coverage is necessary, not sufficient:
  AS -> EU has 99.6% of sites inside the AOA and R2 -0.13.
- MODIS NPP (Asia and North America sites with an NPP value; dropped for lack of NPP: strict 23
  Asian and 38 North American sites, 8 of them west of 125 W; incl_missing 24 and 46, 13 west of
  125 W): NPP adds a small, resolvable gain for AS -> NA (XGBoost +0.025 [0.007, 0.045]
  strict, +0.035 [0.008, 0.062] incl_missing; OLS +0.046 / +0.055) and nothing or a loss for
  NA -> AS (XGBoost -0.028 [-0.066, 0.006] strict, -0.111 [-0.152, -0.075] incl_missing). This
  differs from the audit (brief) "+0.001 [-0.056, 0.055]" result, which used the old site table.
- Tuning sensitivity: see `tuning_sensitivity_summary_<v>.csv` (filled in below).

### Analysis 2 results (`audit/outputs/a2/`)

- One-way random effects (strict; 584 cells with >= 2 records, 2,839 records): within-cell variance
  0.095 [0.082, 0.108], between 0.294 [0.246, 0.348], within share 0.244 [0.209, 0.286]; REML
  agrees (0.095 / 0.332).
- Pair split (cell-weighted half mean squared difference): same study, same year 0.080
  [0.068, 0.093] (2,747 pairs, 400 cells); same study, different years 0.045 [0.036, 0.054] (3,893,
  253); different studies 0.166 [0.124, 0.213] (4,529, 168), of which same year 0.124
  [0.067, 0.195] (403, 55) and different years 0.161 [0.120, 0.207] (4,126, 152). Interannual
  variation within a study is smaller than plot-to-plot variation within a study-year;
  between-study differences dominate. The different-study, same-year count (55 cells) is small.
- Nested components: within-study 0.066 [0.057, 0.075], between-study 0.100 [0.063, 0.145]
  (moments); REML 0.073 and 0.080.
- R2 ceiling for predictors constant within a 0.05-degree cell, site level (strict): B2 (primary)
  0.668 [0.551, 0.769] overall; Asia 0.661, North America 0.669, Europe 0.590, SCA 0.681, Africa
  0.630, Oceania 0.445. Sensitivity: record-count (pair) weighting 0.795; cells with >= 3 records
  0.646; excluding COSORE 0.664; same cells for both pair types 0.624. B1 (one-way, optimistic)
  0.858. B3 (1 - semivariance(0-10 km)/variance) 0.711 [0.501, 0.846] overall, Asia 0.765, North
  America 0.667, Europe 0.404 (wide intervals; 39-189 pairs).
- Observed skill as a fraction of B2 (strict): AS -> NA XGBoost 0.31 [0.15, 0.45]; within-AS 0.32;
  within-NA 0.37; NA -> AS about 0; Europe negative. Measurement noise does not explain the weak
  skill: about two thirds of site-level variance is in principle explainable at 0.05 degrees and
  climate captures about a third of that where it works at all.
- Method and ecosystem: IRGA-IRGA 0.070 [0.060, 0.082] (460 cells); alkali/soda-lime pairs 0.091
  [0.052, 0.136] (52); GC-GC 0.108 (78); IRGA vs alkali/soda lime 0.260 [0.058, 0.589] (8 cells:
  too few to conclude); IRGA vs GC 0.223 [0.136, 0.336] (26). Forest 0.055, grassland 0.115,
  agriculture 0.106, wetland 0.208, mixed ecosystem types in the same cell 0.228: sub-grid land
  cover is a large part of the "noise" for gridded predictors.
- COSORE multi-chamber check: plot-scale variance of log annual Rs between chambers of the same
  site-year 0.13-0.16 (43 dataset-years, 16 datasets), larger than SRDB same-study-same-year pairs
  (which are mostly plot means rather than single chambers).

### Analysis 3 results (`audit/outputs/a3/`, `audit/outputs/srdb_country_check.csv`)

- 13,772 SRDB records with coordinates checked (396 without, 1 out of bounds). 283 (2.1%; 86
  studies) disagree with their Country field beyond 10 km: offshore within 50 km 49, label wrong
  47, longitude sign 44, near border 42, unclear 37, far at sea 29, coordinates wrong (Region names
  a province of the stated country) 14, latitude sign 14, lat/lon swap 4, same-site conflict 3.
  Confidence: 41 high (17 studies), 85 medium, 157 low. 149 flagged records have Rs_annual; 81
  pass every other Step 0 rule (27 studies).
- The four errors named in the brief are all flagged: 13585 and 13587 (Alberta, +111.9 -> lon
  sign, high), 10578 (Mexico City, +99.13 -> lon sign, high), 9842 (Denmark at 55.65 E, falls in
  Russia -> unclear; the Danish ICOS site Sorø is near 11.6 E, so a digit error is likely, but no
  rule proposes that fix).
- SRDB's own checks: the `USA & Longitude > 0` rule in R/srdb_check.R flags 0 records at
  02163a7; the land-mask check is commented out; open issue #50 (2019) lists 80 "low-land" record
  numbers, of which 26 are among my 283 and none among my 41 high-confidence errors. 189 of the 283
  (29 of the 41 high-confidence) fall on land in another country, so no land mask can catch them.
  Closed issue #132 fixed one site of study 4564; record 1543 of the same study (Mols, Denmark)
  is still in the North Sea, and record 1546 (same study, same site name) has the right
  coordinates. Open issue #134 (2022, "Coordinate cleaning") quotes the CoordinateCleaner sentence
  from the Tallo tree-allometry database paper (Jucker et al. 2022, GCB): the maintainer has noted
  the need, and it is not done. Of the 17 high-confidence studies, 16 appear in no SRDB issue or
  pull request; study 4564 appears in closed #132 (which fixed its UK site, not record 1543) and in
  open #72 (collar sizes, not coordinates) (GitHub search API, 34 queries).
- Original rectangles: of the 81 flagged records that pass every other rule, 44 had coordinates
  inside the original "Asia" box and 15 inside the "US" box.
- Effect on transfer metrics (pairs among AS, NA, EU; strict): OLS models change by at most 0.016
  in R2 and 12 g C m-2 yr-1 in RMSE (as-is) and 0.012 / 2 (corrected); XGBoost with fixed
  hyperparameters by at most 0.037 / 10. XGBoost re-tuned on each data set moves by up to 0.10
  (as-is) and 0.17 (corrected) for NA -> AS: tuning instability, not a data effect.
  incl_missing: all |dR2| <= 0.03.
- Draft issue for bpbond/srdb (not posted): `audit/outputs/a3/srdb_issue_draft.md` (41
  high-confidence records, 17 studies, with study titles and DOIs from srdb-studies.csv).

### Checks run

- Every DOI cited is checked against Crossref by `29_crossref_check.py`
  (`audit/outputs/references_crossref.csv`); a reference is used only if status is ok.
- REML vs method-of-moments estimates agree (one-way and nested).
- Multi-record cell share 60.5% reproduces the audit's 61%.
- All transfer comparisons are on identical test sites; paired differences use identical
  bootstrap resamples.
- Independent multi-lens code review (workflow, results below).

### Open questions

1. Keep or drop SRDB Q15 ("seasonal model, not annual") and Q16 ("soil-water model") records?
2. Mexico sits in "South & Central America" (UN subregion). Moving it to North America changes
   both test sets slightly.
3. Low-severity mismatches (near border, < 50 km offshore; 91 records, 41 with Rs that pass other
   rules) are excluded. Treating them as consistent would keep a few coastal sites (for example
   Twin Cays, Belize; Jiuduansha, Yangtze estuary) that are real but missing from 1:10m polygons.
4. The added duplicate rule (decision 4) should be confirmed.
5. COSORE annual records require >= 5 days in every month; >= 1 day would add one dataset.
6. XGBoost selection instability (decision 14) argues for reporting simple models, or ensembles
   over the top configurations, in any final paper.
7. MODIS NPP raster units are the raw GEE export (MOD17 scaling suggests 0.1 g C m-2 yr-1); units
   do not affect the models, but should be documented if NPP is reported.
8. Whether the manuscript should present the ceiling with the nested (B2) or one-way (B1) noise
   model; B2 is better justified but needs the study-effect assumption stated.
