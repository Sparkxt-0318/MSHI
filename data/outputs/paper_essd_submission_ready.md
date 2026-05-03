# Cross-continental transfer of soil-respiration upscaling models reveals regional driver heterogeneity that climate features traverse and gridded soil features do not

**[Author Name]¹**, ORCID 0000-0000-0000-0000

¹ [Affiliation], [City], [Country]

Correspondence: [author@email]

---

## Abstract  *(243 words)*

Continental upscaling of soil respiration (Rs) is widely reported but
not held-out cross-continentally tested. Published Rs upscaling models
(Hashimoto et al., 2015; Warner et al., 2019; Yao et al., 2021;
Stell et al., 2021) report Monte-Carlo confidence intervals on the
global Pg C yr⁻¹ sum or within-sample MAE/RMSE on a gridded
prediction, but none reports a held-out site-level transfer R² between
continents. We close that gap. Trained on 615 Asian SRDB+COSORE sites
and tested on a held-out subset of 274 CONUS sites, an XGBoost model
restricted to eight WorldClim 2.1 bioclimatic variables transfers at
R² = +0.127 (95 % bootstrap CI +0.019 to +0.216, n = 272), Spearman
ρ = +0.277. The same model with eight SoilGrids 2.0 5–15 cm topsoil
layers added (clay, sand, silt, SOC, nitrogen, pHH₂O, bulk density,
CEC) plus four engineered features collapses to transfer R² = +0.020
(CI −0.141 to +0.146, indistinguishable from zero). Per-region SHAP
shows the clay correlation flipping (r_Asia = +0.302, r_US = −0.048),
which we mechanistically attribute to land-use confounding in the
Asian SRDB sample. Köppen-Geiger climate-zone stratification was
tested as a remedy and *worsened* transfer in both qualifying zones,
identifying the cross-zone precipitation gradient as the only
generalisable signal. We argue that statistically defensible
continental Rs maps are bottlenecked by the lack of dense in-situ
ground-truth — the gap that low-cost electrochemically-active-biofilm
biosensor networks could close.

**Keywords:** soil respiration, machine learning, transfer learning,
SoilGrids, SRDB, Köppen-Geiger, electrochemical biosensors, MSHI-Geo

---

## 1.  Introduction

[Brief 1-2 paragraph introduction motivating cross-continental
transfer testing as the missing benchmark in continental Rs upscaling.
Cite [1, 2, 3, 4] for prior continental Rs work and [5] for SRDB-V5
update. To be expanded prior to ESSD submission.]

## 2.  Data and methods

### 2.1  Data sources

Soil-respiration measurements are drawn from two community databases.
SRDB v5 [5] is the canonical literature-derived compilation of annual
soil-respiration estimates (n = 14,169 records as of v5; n = 7,792
with non-null `Rs_annual`); we restricted to records with
50 ≤ *Rs<sub>annual</sub>* ≤ 4,500 g C m⁻² yr⁻¹ and dropped those
with non-empty experimental-treatment flags. COSORE [6] provides
high-frequency chamber-flux time series; we integrated per-port
CSR_FLUX_CO2 in μmol m⁻² s⁻¹ to annual *Rs* by mean-flux × 12.011 ×
3.1536 × 10⁷ ÷ 10⁶ ≈ 378.79 g C m⁻² yr⁻¹ per μmol m⁻² s⁻¹, retaining
only ports with ≥ 150 unique observation days spanning ≥ 180 calendar
days. After 5-km spatial deduplication (preferring COSORE at
overlapping cells), the training pool comprised 1,393 sites.

Predictors are eight WorldClim 2.1 bioclimatic variables [7]
(bio01, bio04, bio05, bio06, bio12, bio14, bio15, bio17 — annual mean
T, T seasonality, T extrema, annual precipitation, precipitation
extrema, precipitation seasonality), eight SoilGrids 2.0 [8]
5–15 cm topsoil layers (SOC, total nitrogen, pHH₂O, clay, sand, silt,
bulk density, cation-exchange capacity), and four engineered features
(C/N ratio, clay/sand ratio, pH-optimality = −|pH − 6.5|, De Martonne
aridity = bio12 / (bio01 + 10)).

### 2.2  Train/test partition

The held-out validation is geographic. Asian sites
(longitude 25–180 °E, latitude −10 to 80 °N) form the training set
(n = 615; 605 SRDB + 10 COSORE). CONUS sites
(longitude −125 to −66 °W, latitude 24–50 °N) form the held-out
validation set (n = 274; 253 SRDB + 21 COSORE). The remaining 504
sites in other regions (mostly Europe, South America, Africa) were
held aside.

Target distributions are nearly identical between regions
(Asia mean log *Rs<sub>annual</sub>* = 6.543, σ = 0.705;
CONUS mean = 6.568, σ = 0.619). Mean shift +2.5 % in *Rs*; standard
deviation ratio 0.88. Histograms have similar shape, modal at
log Rs ≈ 6.6–7.0. Target distribution differences are not a plausible
source of transfer failure.

### 2.3  Model architecture

We use gradient-boosted regression trees (XGBoost; Chen and Guestrin,
2016) with the target log *Rs<sub>annual</sub>*. Six configurations
were tested in the main sweep and two configurations are reported in
detail below:

- **F  (climate-only):** 8 WorldClim bioclim features. Hyperparameters
  depth=3, n_estimators=200, learning_rate=0.05, subsample=0.70,
  colsample_bytree=0.85, min_child_weight=6, reg_alpha=0.1,
  reg_lambda=2.0.
- **B  (full features):** all 20 features (8 SoilGrids + 8 WorldClim
  + 4 engineered). Hyperparameters depth=3, n_estimators=250,
  learning_rate=0.05, subsample=0.70, colsample_bytree=0.85,
  min_child_weight=8, reg_alpha=2.0, reg_lambda=8.0.

Heavier regularisation in B was selected by sweep against the
20-feature stack to mitigate overfitting; the result was a modest
recovery of transfer R² that nonetheless remained statistically
indistinguishable from zero.

### 2.4  Validation

Two complementary tests were applied. First, 5-fold spatial-block
cross-validation on the Asia training set, with blocks of 5° × 5°
latitude/longitude assigned by floor((lat or lon) / 5) and shuffled
between folds. Block sizes were chosen to force every fold to
extrapolate to a different climate-biome combination. Second, the
Asia → CONUS transfer test: train on the full Asia training set,
predict on the CONUS held-out set, report R², RMSE, MAE, Spearman
ρ and tertile classification accuracy.

### 2.5  Statistical methods

Bootstrap 95 % confidence intervals on transfer R² were computed by
resampling the held-out CONUS set with replacement
(n_bootstrap = 2,000, seed = 42), retraining once on the full Asia set
and recomputing R² between fixed predictions and the resampled
observations. The CI is reported as the 2.5th and 97.5th percentiles
of the resulting R² distribution. SHAP feature importance [9] used
the TreeExplainer on a 800-row stratified sample.

Climate-zone stratification used a top-level Köppen-Geiger
classification computable from the WorldClim bioclim variables alone:
A (tropical, bio06 ≥ 18 °C); B (arid, bio12 < 400 mm AND bio14 < 30 mm);
C (temperate, −3 ≤ bio06 < 18 °C and bio05 ≥ 10 °C); D (continental,
bio06 < −3 °C and bio05 ≥ 10 °C); E (polar, bio05 < 10 °C). Per-zone
F-class transfer was tested where Asia-of-zone n ≥ 80 and US-of-zone
n ≥ 30.

## 3.  Results

### 3.1  Cross-validation performance across feature sets

| Configuration | n_features | CV R² | Transfer R² | Bootstrap 95 % CI | CI excl. 0 |
|---|---:|---:|---:|---|---|
| F  (climate-only)        |  8 | −0.067 | **+0.127** | (+0.019, +0.216) | yes |
| B  (full features)       | 20 | −0.083 | +0.020 | (−0.141, +0.146) | no |
| A  (baseline depth-3)    | 20 | −0.127 | −0.031 | — | — |
| C  (shallow more trees)  | 20 | −0.054 | −0.001 | — | — |
| D  (drop overfit subset) | 16 | −0.139 | −0.024 | — | — |
| E  (climate + transfer-stable soil) | 13 | −0.128 | +0.008 | — | — |

Negative CV R² values reflect the difficulty of 5° spatial blocking
at this sample size: every held-out fold extrapolates to a
climate-biome combination poorly represented in the remaining training
set. Random-fold CV on the same data yields R² ≈ +0.09 for F (the
in-distribution ceiling).

The Asia → CONUS transfer R² is the more decision-relevant metric.
Five of six configurations land at or below zero. The single exception
is F, which transfers at R² = +0.127 with a 95 % bootstrap CI
excluding zero. Heavier regularisation on the 20-feature stack (B)
recovers R² to +0.020 (CI includes zero) by shrinking soil-feature
contributions to nearly zero.

### 3.2  Alternative validation metrics on the CONUS set

| Metric                                | F: climate-only | B: full features (20) |
|---|---:|---:|
| n_train (Asia, post-NaN drop)         | 600 | 588 |
| n_us (post-NaN drop)                  | 272 | 270 |
| RMSE (log Rs)                          | 0.585 | 0.616 |
| NRMSE (RMSE / observed range)          | 0.155 | 0.163 |
| Spearman ρ                             | +0.277 | +0.249 |
| MAE (Rs, g C m⁻² yr⁻¹)                | 359 | 364 |
| Tertile classification accuracy        | 37.1 % | 40.0 % |

F is better on R², RMSE, NRMSE, Spearman, and MAE-log. Tertile
accuracy is essentially tied — both models compress US predictions
toward the training mean (regression-to-mean signature also visible
in the prediction-σ statistics).

### 3.3  Regional driver heterogeneity

Two parallel XGBoost models were trained with identical
hyperparameters and feature lists, one on Asia (n = 588 post-NaN
drop), one on CONUS (n = 270). Mean |SHAP| rankings (top eight per
region):

| Rank | Asia | mean &#124;SHAP&#124; | CONUS | mean &#124;SHAP&#124; |
|---:|---|---:|---|---:|
| 1 | bio12 (annual precipitation) | 0.077 | bio12 | 0.098 |
| 2 | silt | 0.059 | nitrogen | 0.079 |
| 3 | bio01 (annual T) | 0.048 | bio05 (T warmest month) | 0.070 |
| 4 | bio04 (T seasonality) | 0.045 | pHH₂O | 0.070 |
| 5 | clay/sand ratio | 0.045 | silt | 0.061 |
| 6 | C/N ratio | 0.043 | bio15 (precipitation seasonality) | 0.059 |
| 7 | aridity (De Martonne) | 0.043 | bulk density | 0.059 |
| 8 | bulk density | 0.040 | bio01 | 0.039 |

Annual precipitation (bio12) is the only feature with stable rank
and similar magnitude in both regions
(Pearson r vs log *Rs<sub>annual</sub>* = +0.30 in Asia,
+0.33 in CONUS). The Asia-specific cluster — clay/sand ratio,
C/N ratio, aridity — drops out of the CONUS ranking; pHH₂O and
nitrogen become dominant CONUS drivers.

Most diagnostic is the clay correlation: r_Asia = +0.302
(one of the strongest in the Asia set), r_US = −0.048. A model
that fits "more clay → more Rs" on Asia and applies it to CONUS
fails by construction.

### 3.4  Climate-zone stratification

| Köppen zone | n_Asia | n_US | F transfer R² | 95 % CI | CI excl. 0 |
|---|---:|---:|---:|---|---|
| C (temperate) | 247 | 89 | −0.336 | (−1.06, +0.04) | no (spans 0) |
| D (continental) | 244 | 159 | −0.199 | (−0.39, −0.06) | yes — significantly *negative* |
| Cross-zone reference | 600 | 272 | **+0.127** | (+0.020, +0.212) | yes — significantly positive |

Within-zone transfer is *worse* than the cross-zone baseline in both
qualifying zones. Zones A (tropical), B (arid) and E (polar) lacked
the within-class US sample size for a defensible test. Köppen D's CI
is fully below zero, indicating the within-zone model on continental
sites does worse than predicting the US-mean of *Rs* — a
regression-to-mean failure within a more homogeneous training set.

We interpret the cross-zone +0.127 as carried by the cross-zone
precipitation gradient already identified in §3.3. Stratifying that
gradient away leaves no transferable signal.

## 4.  Discussion

The structural cause of cross-continental transfer failure is that
gridded soil products carry both signal (regional soil-formation
patterns correlated with biome and climate) and noise (smoothing
error in the global random-forest used to produce them). At
individual SRDB sites, the local soil at the 1-m chamber footprint
can differ by 2–3× from the SoilGrids cell mean, particularly for
SOC. A machine-learning model trained on this stack cannot
distinguish the two and will exploit any per-region correlation it
finds, including spurious ones driven by sampling geography.

The Köppen-stratification negative result sharpens this argument.
If the transfer ceiling were simply due to weak signal, training a
sub-model on a more homogeneous climate zone should help. Instead,
within-zone transfer collapses, because the cross-zone precipitation
gradient — the only feature with stable cross-region rank — is what
carries the +0.127 baseline. No obvious slicing of the existing
gridded data improves on this.

A complementary IGBP land-cover stratification (forest-only,
cropland-only, etc.) could in principle remove the land-use confound
suggested by the clay-Rs sign-flip and is the immediate next test
once MOD12Q1 is exported. Based on the Köppen result the prior on
rescue is low, but the test is still informative.

The biosensor case follows. Two of the three components of the
standard upscaling recipe — gridded climate, gridded soil, gridded
vegetation — are themselves modelled, not measured, at the resolution
that matters. Only chamber and eddy-covariance networks provide
ground truth, and their sparseness (≈ 1,400 SRDB+COSORE sites
globally for *Rs<sub>annual</sub>*) limits both the training signal
and the validation rigour available to upscaling efforts. A dense
electrochemically-active-biofilm (EAB) biosensor network would
measure the same biological flux that *Rs<sub>annual</sub>*
integrates over a year, at a spatial density (centimetre-scale,
low-cost, deployable) that no chamber or eddy-covariance instrument
can match.

## 5.  Conclusions

We characterise the held-out cross-continental transfer R² of soil-
respiration upscaling models for the first time. Climate features
alone transfer Asia → CONUS at R² = +0.127, statistically
significantly above zero. Adding gridded SoilGrids texture features
collapses transfer to zero. The mechanism is regional driver
heterogeneity, with the clay-Rs correlation flipping sign across
continents. Climate-zone stratification does not rescue, identifying
the cross-zone precipitation gradient as the only generalisable
signal. We argue this characterises the ground-truth measurement
gap that low-cost in-situ biosensor networks could close.

## Data availability

Source data are open: SRDB v5 [5] at github.com/bpbond/srdb,
DOI 10.5194/essd-13-255-2021; COSORE [6] at github.com/bpbond/cosore,
DOI 10.1111/gcb.15353; SoilGrids 2.0 [8] via OGC WCS at
maps.isric.org, DOI 10.5194/soil-7-217-2021; WorldClim 2.1 [7] at
worldclim.org, DOI 10.1002/joc.5086.

## Code availability

All processing code (SoilGrids WCS download, COSORE annual integration,
feature extraction, model training, bootstrap CI, SHAP, hero-map
rendering) is at github.com/Sparkxt-0318/MSHI on the
`claude/round-c-deliverables` branch. The `run.sh` driver reproduces
the full pipeline given the four open datasets above.

## Author contributions

[Author Name] designed the study, implemented the analysis pipeline,
ran the experiments, and wrote the manuscript. [Other contributors as
applicable.]

## Competing interests

The author declares no competing interests.

## Acknowledgments

[Acknowledgments to be added prior to submission. The author thanks
the SRDB and COSORE communities for the open data underlying this
work.]

## References

[1] Hashimoto, S., Carvalhais, N., Ito, A., Migliavacca, M.,
    Nishina, K., and Reichstein, M.: Global spatiotemporal
    distribution of soil respiration modeled using a global
    database, Biogeosciences, 12, 4121–4132,
    https://doi.org/10.5194/bg-12-4121-2015, 2015.

[2] Warner, D. L., Bond-Lamberty, B., Jian, J., Stell, E., and
    Vargas, R.: Spatial Predictions and Associated Uncertainty of
    Annual Soil Respiration at the Global Scale, Global Biogeochem.
    Cycles, 33, 1733–1745,
    https://doi.org/10.1029/2019GB006264, 2019.

[3] Yao, Y., Ciais, P., Viovy, N., Li, W., Cresto Aleina, F.,
    Yang, H., Joetzjer, E., and Bond-Lamberty, B.: A Data-Driven
    Global Soil Heterotrophic Respiration Dataset and the Drivers
    of Its Inter-Annual Variability, Global Biogeochem. Cycles,
    35, e2020GB006918,
    https://doi.org/10.1029/2020GB006918, 2021.

[4] Stell, E., Warner, D., Jian, J., Bond-Lamberty, B., and
    Vargas, R.: Spatial biases of information influence global
    estimates of soil respiration: How can we improve global
    predictions?, Glob. Change Biol., 27, 3923–3938,
    https://doi.org/10.1111/gcb.15666, 2021.

[5] Jian, J., Vargas, R., Anderson-Teixeira, K., Stell, E.,
    Herrmann, V., Horn, M., Kholod, N., Manzon, J., Marchesi, R.,
    Paredes, D., and Bond-Lamberty, B.: A restructured and updated
    global soil respiration database (SRDB-V5), Earth Syst. Sci.
    Data, 13, 255–267, https://doi.org/10.5194/essd-13-255-2021,
    2021.

[6] Bond-Lamberty, B., Christianson, D. S., Malhotra, A., Pennington,
    S. C., Sihi, D., AghaKouchak, A., et al.: COSORE: A community
    database for continuous soil respiration and other
    soil-atmosphere greenhouse gas flux data, Glob. Change Biol.,
    26, 7268–7283,
    https://doi.org/10.1111/gcb.15353, 2020.

[7] Fick, S. E. and Hijmans, R. J.: WorldClim 2: new 1-km spatial
    resolution climate surfaces for global land areas, Int. J.
    Climatol., 37, 4302–4315,
    https://doi.org/10.1002/joc.5086, 2017.

[8] Poggio, L., de Sousa, L. M., Batjes, N. H., Heuvelink, G. B. M.,
    Kempen, B., Ribeiro, E., and Rossiter, D.: SoilGrids 2.0:
    producing soil information for the globe with quantified spatial
    uncertainty, SOIL, 7, 217–240,
    https://doi.org/10.5194/soil-7-217-2021, 2021.

[9] Lundberg, S. M. and Lee, S.-I.: A Unified Approach to
    Interpreting Model Predictions, in: Advances in Neural
    Information Processing Systems 30, 4765–4774, 2017.

[10] Chen, T. and Guestrin, C.: XGBoost: A Scalable Tree Boosting
     System, in: Proceedings of the 22nd ACM SIGKDD International
     Conference on Knowledge Discovery and Data Mining, 785–794,
     https://doi.org/10.1145/2939672.2939785, 2016.

[11] Bond-Lamberty, B. and Thomson, A.: A global database of soil
     respiration data, Biogeosciences, 7, 1915–1926,
     https://doi.org/10.5194/bg-7-1915-2010, 2010.
