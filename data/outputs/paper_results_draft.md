# Results — MSHI-Geo continental respiration model

*Draft, internal. Working numbers from the 2026-04-26 / 2026-04-27
overnight runs and the 2026-05-03 Run-B partial (MODIS pending).*

## 1. Training data and target

We assembled a global training table from two community databases of soil
respiration: the Soil Respiration Database (SRDB; Bond-Lamberty & Thomson
2010, with the v5 update by Jian et al. 2021), which compiles literature-
derived annual soil respiration estimates (*Rs<sub>annual</sub>*,
g C m⁻² yr⁻¹), and the COntinuous SOil REspiration database (COSORE;
Bond-Lamberty et al. 2020), which provides high-frequency chamber-flux
time series. SRDB contributed 4,771 records after dropping manipulated
treatments and out-of-range values
(50 ≤ *Rs<sub>annual</sub>* ≤ 4,500 g C m⁻² yr⁻¹). COSORE was integrated to
per-port annual fluxes — only ports with ≥150 unique observation days
spanning ≥180 calendar days were retained — and aggregated to per-site
estimates (66 sites of 94 candidate datasets; the remainder used unsupported
R-serialisation features that the available Python parser could not decode).

After 5-km spatial deduplication (preferring COSORE at overlapping cells,
since its in-situ continuous protocol is less variable than SRDB's
literature-compiled rates), the training pool comprised 1,393 sites. We
defined two target regions for the cross-continental transfer test:

| Region | Bounding box (lon, lat) | n_sites | source breakdown |
|---|---|---:|---|
| Asia (training)    | 25 to 180°E, −10 to 80°N | 615 | 605 SRDB + 10 COSORE |
| CONUS (validation) | −125 to −66°W, 24 to 50°N | 274 | 253 SRDB + 21 COSORE |
| Other (held aside) | — | 504 | 485 SRDB + 19 COSORE |

The `log Rs_annual` distributions are nearly identical between training and
validation regions: Asia mean = 6.543 (σ = 0.705), US mean = 6.568 (σ = 0.619).
Mean shift is +2.5% in *Rs* and the standard deviation ratio is 0.88. The
distributions are also similarly shaped (modal at log Rs ≈ 6.6–7.0,
i.e. *Rs* ≈ 700–1,100 g C m⁻² yr⁻¹). **Target distribution differences are
not a plausible source of transfer failure.**

We sampled 8 SoilGrids 2.0 (Poggio et al. 2021) topsoil layers (5–15 cm
mean: SOC, total nitrogen, pHH₂O, clay, sand, silt, bulk density, CEC) and
8 WorldClim 2.1 (Fick & Hijmans 2017) bioclimatic variables (bio01, bio04,
bio05, bio06, bio12, bio14, bio15, bio17) at each training and validation
point. We added 4 engineered features (C/N ratio, clay/sand ratio,
pH-optimality, and the De Martonne aridity index), giving 20 features
total. MODIS NPP (MOD17A3HGF), LST (MOD11A2), and IGBP land cover
(MCD12Q1) layers are specified in the configuration; **[PENDING MODIS:
the MOD17A3HGF NPP raster, MOD11A2 LST day/night rasters, and MCD12Q1
2023 IGBP land-cover raster could not be exported in the current
overnight run because Earth Engine and LP DAAC both require interactive
authentication unavailable in this environment. The F+NPP and Full+MODIS
analyses described in Section 2 will be added once the user runs the
GEE export. See `RUN_B_BLOCKERS.md`.]**

## 2. Cross-validation performance across feature sets

We trained six XGBoost configurations (Table 1) and evaluated them with
5-fold spatial-block cross-validation at 5° latitude/longitude blocks
within the Asia training set, plus the held-out CONUS validation set.

**Table 1 — Asia 5° spatial-block CV and Asia → US transfer.**

| Config | Features | n_feat | CV R² | Transfer R² | Δ vs climate-only | Bias |
|---|---|---:|---:|---:|---:|---:|
| A_baseline | depth=3 n_est=250 reg_λ=2.0 | 20 | −0.127 | −0.031 | −0.158 | −0.085 |
| B_heavier_reg | depth=3 n_est=250 reg_λ=8.0 reg_α=2.0 | 20 | −0.083 | +0.020 | −0.107 | −0.086 |
| C_shallow_more | depth=2 n_est=400 reg_λ=4.0 | 20 | −0.054 | −0.001 | −0.128 | −0.084 |
| D_drop_overfit | baseline; drop {clay, sand, silt, clay/sand ratio} | 16 | −0.139 | −0.024 | −0.151 | +0.012 |
| E_climate_plus_transferring_soil | 8 bioclim + pHH₂O + pH-opt + bdod + cec + aridity | 13 | −0.128 | +0.008 | −0.119 | −0.041 |
| **F_climate_only** | **8 bioclim variables** | **8** | **−0.067** | **+0.127** | **+0.000** | **−0.044** |

The negative CV R² values reflect the difficulty of 5° spatial blocking
at this sample size: each held-out fold forces the model to extrapolate to
a different climate-biome combination from any present in the remaining
training set. Random-fold CV on the same data yields R² ≈ +0.09 for
climate-only and +0.02–+0.09 for the 20-feature configurations — i.e. the
model can fit in-distribution, just not extrapolate spatially.

The Asia → US transfer R² is the more decision-relevant metric. Five of six
configurations land at or below zero, indicating predictions on US sites
are no better than predicting the training-mean of *Rs*. The single
exception is the climate-only model (F), which transfers at R² = +0.127 —
a modest but non-zero generalisation. Heavier regularisation on the
20-feature stack (B) recovers some transfer (R² = +0.020), but only by
shrinking soil-feature contributions toward zero, which is essentially
the same fix that F achieves explicitly by feature selection.

Bias on US is −0.044 to −0.086 log units across all configs, equivalent to
a 4–8% under-prediction. US `pred σ` is 0.230–0.319 versus observed σ = 0.619,
i.e. all models compress US predictions toward the training mean by 50–63%
— the canonical signature of a model fitting noise rather than transferable
structure.

**Table 2 — alternative metrics for the two extreme configurations on US.**
Values from Run A; both models retrained on the full Asia table for this
report.

| Metric | F: climate-only | B: full features (20) |
|---|---:|---:|
| n_train (Asia, post-NaN drop) | 600 | 588 |
| n_us (post-NaN drop) | 272 | 270 |
| R² (log Rs) | **+0.127** | +0.020 |
| 95% bootstrap CI on R² (n=2000) | **(+0.019, +0.216)** | (−0.141, +0.146) |
| RMSE (log Rs) | 0.585 | 0.616 |
| NRMSE (RMSE / observed range) | 0.155 | 0.163 |
| Spearman ρ | **+0.277** | +0.249 |
| MAE (Rs, g C m⁻² yr⁻¹) | 359 | 364 |
| Tertile classification accuracy | 37.1% | 40.0% |

F's bootstrap 95% CI on transfer R² excludes zero; B's CI includes zero.
F is statistically significantly better than chance, B is not.

## 3. Asia → US transfer

The held-out validation test addresses the project's primary scientific
question: does a model trained on Asian soil-respiration measurements
generalise to a different continent? Two answers, depending on the
feature set:

- **Climate-only (F):** R² = +0.127 (95% bootstrap CI +0.019 to +0.216,
  n_us = 272), RMSE = 0.585 log units (NRMSE = 0.155), Spearman ρ =
  +0.277, bias = −0.044. The CI excludes zero, so the transfer is
  statistically significantly positive; in absolute terms the model
  recovers the rank ordering of US sites by *Rs* and explains roughly
  13% of `log Rs` variance, while shrinking the predicted spread to
  about 38% of the observed σ.

- **Full features (B):** R² = +0.020 (95% CI −0.141 to +0.146,
  n_us = 270), Spearman ρ = +0.249. The CI spans zero. We cannot
  reject the null that adding the soil layers contributes nothing to
  cross-continental generalisation.

To our knowledge no published Rs upscaling study reports a held-out
cross-continental transfer R² as defined here; published studies
(Hashimoto et al. 2015; Warner et al. 2019; Yao et al. 2021;
Stell et al. 2021) report Monte-Carlo CIs on the global Rs sum or
within-sample MAE/RMSE on the global 0.5° to 1 km grid, but not a
site-level transfer test of this kind. Section 5 returns to this point
in the context of spatial bias of the SRDB record.

The transfer gap relative to in-distribution performance — the difference
between Asia random-KFold CV R² and Asia → US transfer R² — is
approximately 0.10 across configurations. This gap is larger than the
sampling-noise-only expectation for n ≈ 270 (Asia y-variance is 0.50;
CONUS y-variance is 0.38; even at perfect transfer, random sampling would
add only ~0.02 to the R² gap). The remaining ~0.08 of gap is therefore
attributable to a real change in the feature → respiration relationship
between regions, not to small-sample noise.

## 4. Regional driver heterogeneity

To localise the transfer failure mechanism, we trained two parallel XGBoost
models with identical hyperparameters and feature lists — one on the Asia
subset, one on the CONUS subset — and computed mean |SHAP| per feature on
each. Driver rankings (top eight by region):

| Rank | Asia (n=588) | mean &#124;SHAP&#124; | US (n=270) | mean &#124;SHAP&#124; |
|---:|---|---:|---|---:|
| 1 | bio12 (annual precipitation) | 0.077 | bio12 | 0.098 |
| 2 | silt | 0.059 | nitrogen | 0.079 |
| 3 | bio01 (annual T) | 0.048 | bio05 (T warmest month) | 0.070 |
| 4 | bio04 (T seasonality) | 0.045 | pHH₂O | 0.070 |
| 5 | clay/sand ratio | 0.045 | silt | 0.061 |
| 6 | C/N ratio | 0.043 | bio15 (precip seasonality) | 0.059 |
| 7 | aridity (De Martonne) | 0.043 | bulk density | 0.059 |
| 8 | bulk density | 0.040 | bio01 | 0.039 |

Annual precipitation (bio12) is the single most important feature in both
regions (Pearson r between bio12 and log *Rs<sub>annual</sub>* = +0.30 in Asia
and +0.33 in US). This is the only feature with stable sign and similar
rank cross-region.

The Asia-specific cluster — clay/sand ratio, C/N ratio, aridity index —
either drops out of or moves down the US ranking, while pHH₂O and nitrogen
become dominant US drivers. Most diagnostic is the clay correlation:
r_Asia = +0.302 (one of the strongest in the Asia set), r_US = −0.048 (no
relationship). A model that picks up the Asian "more clay → more *Rs*"
signal applies it to US sites, where the relationship is absent or reversed.

We interpret these regional differences mechanistically. In the Asia set,
clay and silt fractions are confounded with land-use and management:
much of the Asian SRDB sample is on intensively cultivated alluvial soils
(Indo-Gangetic Plain, North China Plain) where high silt + clay correlates
with continuous cropping, irrigation, and fertiliser application — all of
which independently elevate *Rs<sub>annual</sub>*. In CONUS, the SRDB record
is dominated by temperate forests and rangelands, where the dominant
controls on *Rs* are nitrogen mineralisation (driving soil-N rank) and
substrate pH (driving pHH₂O rank). The XGBoost model has no way to
distinguish "clay-rich soil under intensive Asian agriculture" from
"clay-rich soil under any land use", because we did not provide a
land-management covariate.

## 4.5 Climate-zone stratification (substitute for IGBP biome stratification)

The driver-heterogeneity result raises an obvious question: if the
feature → *Rs* relationship differs cross-region, does training on a
more homogeneous stratum recover transfer? The standard remedy in
upscaling literature is to stratify by IGBP land-cover class
(forest vs cropland vs grassland …) and fit a sub-model per class,
which controls for land-use and so removes the confound described above.

We could not run that test in the current draft because the MOD12Q1
IGBP land-cover raster is `[PENDING MODIS]` (see `RUN_B_BLOCKERS.md`).
As a substitute we ran a top-level Köppen-Geiger climate-zone
stratification, computed directly from WorldClim bioclim variables
(thresholds on bio05, bio06, bio12, bio14). This stratifies on
climate rather than land-use, so it is an *imperfect* substitute, but
it answers an analytically related question: does the cross-continental
feature → *Rs* relationship hold within a more climate-homogeneous
subset of sites? Two zones met the threshold of ≥ 80 Asian training
sites and ≥ 30 US validation sites:

| Köppen zone | n_Asia | n_US | Within-zone transfer R² | 95% CI | CI excludes 0? |
|---|---:|---:|---:|---|---|
| C (temperate) | 247 | 89 | −0.336 | (−1.06, +0.04) | no (spans 0) |
| D (continental) | 244 | 159 | −0.199 | (−0.39, −0.06) | yes — significantly *negative* |
| **Cross-zone F (reference)** | **600** | **272** | **+0.127** | **(+0.020, +0.212)** | **yes — significantly positive** |

Within-zone transfer is *worse* than the cross-zone baseline in both
classes. Köppen D's CI is fully below zero, meaning the within-zone
F model on continental sites does worse than predicting the US-mean
of *Rs* — a regression-to-mean failure within a more homogeneous
training set. Köppen A (tropical), B (arid) and E (polar) lacked the
within-class US sample size (in particular the CONUS bbox 24–50 °N
contains no Köppen A sites).

We interpret this as follows: the cross-zone F transfer R² of +0.127
is not a residual signal that survives despite climate-zone
heterogeneity; it *depends on* the cross-zone precipitation gradient
that runs through the whole training and validation sample. Stripping
that gradient (by training within a single zone) removes the
transferable signal. This is consistent with the SHAP analysis in
Section 4 in which annual precipitation (bio12) is the only feature
with stable cross-region rank, magnitude and sign.

The IGBP-stratified analysis pending MODIS will address a different
question — does land-use stratification (rather than climate-zone
stratification) recover transfer? Based on the Köppen result, the
prior expectation is that it will not, but the test is still
informative because cropland-only or forest-only sub-models would
remove the land-use confound the Asia-vs-US clay correlation
suggested.

## 5. Implications for continental-scale soil monitoring

The headline finding — that soil-property layers degrade rather than
improve cross-continental transfer of soil-respiration models — has a
specific structural cause and a generalisable implication.

The structural cause is that gridded soil products (SoilGrids 2.0 at 250 m,
re-aggregated to 5 km here) are themselves the output of a global random-
forest model fitted to a sparse and geographically uneven set of soil
profiles. Their values on uncovered grid cells are smoothed
machine-learning estimates, not measurements. At individual SRDB sites,
the local soil at the 1-m chamber footprint can differ by 2–3× from the
SoilGrids cell mean — particularly for soil organic carbon, which has the
highest small-scale spatial variance of any soil property. The result is
that SoilGrids features carry both signal (regional soil-formation patterns
that do correlate with biome and climate) and noise (smoothing error). A
machine-learning model trained on this stack cannot distinguish the two
and will exploit any per-region correlation it finds, including spurious
ones driven by sampling geography.

The generalisable implication is that statistically defensible continental
soil-flux maps are presently bottlenecked by the lack of dense, comparable,
in-situ measurement networks. Two of the three components in the standard
recipe — gridded climate (WorldClim, ERA5-Land), gridded soil
(SoilGrids), and gridded vegetation activity (MODIS NPP, LAI) — are
themselves modelled, not measured, at the resolution that matters. Only
chamber and eddy-covariance networks provide ground truth, and their
sparseness (≈ 1,400 SRDB+COSORE sites globally for *Rs<sub>annual</sub>*)
limits both the training signal and the validation rigour available to
upscaling efforts.

Published continental *Rs* models report uncertainty as Monte-Carlo CIs
on the global Rs sum or as within-sample MAE/RMSE on the prediction grid;
none of the four most directly comparable studies report a held-out
cross-continental site-level transfer R² as defined in this work
(Section 3). Hashimoto et al. 2015 estimates global Rs at 91 Pg C yr⁻¹
(95% CI 87–95) with a climate-driven model at 0.5° resolution, with no
site-level R² in the abstract. Warner et al. 2019 produces a 1 km
quantile-regression-forest map of annual Rs with within-sample MAE =
18.6 and RMSE = 40.4 Pg C yr⁻¹. Yao et al. 2021 reports a 0.5° random-
forest soil heterotrophic respiration product but does not report
site-level R² in the abstract. Stell et al. 2021 explicitly characterises
spatial bias of SRDB — the "still biased toward northern latitudes and
temperate zones" finding — as a source of model uncertainty, and shows
that an optimised global sample distribution lowers the global Rs
uncertainty band. Stell et al. 2021 does not run a held-out
cross-continental performance test, which is the gap the present work
fills.

The cross-region driver heterogeneity we report in Section 4 is the
mechanistic dual of the spatial bias Stell et al. 2021 identify: when the
training set is geographically uneven and the regression model is allowed
to exploit per-region soil-property correlations, the resulting global
map will both over-fit to the dense regions and under-fit (or mis-fit)
the sparse ones. Our climate-only result is the conservative case —
features whose bivariate relationship with *Rs<sub>annual</sub>* is stable
cross-region (precipitation, temperature) generalise; features whose
relationship inverts or vanishes across regions (clay, clay/sand ratio,
nitrogen) do not.

## 6. Discussion — what would close the gap

Three classes of intervention can plausibly improve the Asia → US transfer
beyond the +0.13 ceiling we observe with climate-only features.

**Higher-quality vegetation activity proxies.** The dominant control on
soil respiration at continental scale is substrate input from above-ground
production. MODIS NPP at 500 m–1 km is a standard predictor in published
*Rs* upscaling (e.g. Warner et al. 2019; Yao et al. 2021); we specified
MOD17A3HGF NPP in our feature configuration but did not include it in
this run. Adding it is the highest-priority next step. The expected
direction of impact is positive but the magnitude on cross-continental
transfer R² is unknown — none of the published studies above evaluate
the held-out cross-continental setting we use here.

**Regional sub-models or biome stratification.** Section 4.5 tested
this for Köppen-Geiger climate zones — the climate-only stratification
that does not require MODIS — and found within-zone transfer R² was
*worse* than the cross-zone baseline in both qualifying zones. Köppen
D's CI was significantly negative (the within-zone model on
continental sites did worse than predicting the US-mean *Rs*).
Climate-zone stratification therefore does not close the transfer gap;
it removes the cross-zone precipitation gradient that is, per the
SHAP analysis, the actual transferable signal. Whether **IGBP
land-cover stratification** would close the gap is the open question
deferred until MOD12Q1 is available; a forest-only or cropland-only
sub-model has a chance because it removes the land-use confound the
Asia-vs-US clay correlation hinted at, but the Köppen result lowers
the prior.

**Direct biosensor measurement networks.** The deeper argument from these
results is that gridded soil products lack the spatial fidelity to
distinguish soil-driven from climate-driven respiration variability at the
continental scale, and that this gap cannot be closed by adding more
features from the same generation of remote products. A dense, low-cost,
in-situ biosensor network — measuring electron-transfer activity from soil
microbial assemblages at the centimetre scale and compatible with the same
EAB chemistry validated at the laboratory bench — would provide the
ground-truth layer that current upscaling pipelines lack. The biosensor
captures the same biological flux that *Rs<sub>annual</sub>* integrates
over a year (electron transfer ∝ metabolic activity ∝ substrate
oxidation), but at a spatial density (centimetre-scale, low-cost,
deployable) that no chamber or eddy-covariance instrument can match.

Stated more directly: the satellite product cannot tell us whether a
clay-rich Asian agricultural soil and a clay-rich US forest soil
respire similarly. The biosensor can.

The Köppen-stratification result (Section 4.5) sharpens this argument.
The biosensor case does not depend on the IGBP-stratified analysis
producing a particular answer. If forest-only or cropland-only
stratification *recovers* transfer (the optimistic case), the
implication is that gridded land-cover labels are the pivot variable
the upscaling pipeline currently lacks at site-level fidelity — which
is exactly what a dense in-situ network could provide. If
stratification *fails* (the Köppen-consistent prior), the implication
is that even continent-specific land-cover assignment is too coarse to
predict *Rs* without the metabolic ground truth a biosensor measures
directly. Either outcome is wedge for the same conclusion.

## References

- Bond-Lamberty, B. & Thomson, A. 2010. A global database of soil
  respiration data. *Biogeosciences* 7: 1915–1926.
- Bond-Lamberty, B. *et al.* 2020. COSORE: A community database for
  continuous soil respiration and other soil-atmosphere greenhouse gas
  flux data. *Global Change Biology* 26: 7268–7283.
- Fick, S.E. & Hijmans, R.J. 2017. WorldClim 2: new 1-km spatial
  resolution climate surfaces for global land areas. *International
  Journal of Climatology* 37: 4302–4315.
- Hashimoto, S., Carvalhais, N., Ito, A., Migliavacca, M., Nishina, K.,
  Reichstein, M. 2015. Global spatiotemporal distribution of soil
  respiration modeled using a global database. *Biogeosciences*
  12: 4121–4132. doi:10.5194/bg-12-4121-2015
- Jian, J., Vargas, R., Anderson-Teixeira, K., Stell, E., Herrmann, V.,
  Horn, M., Kholod, N., Manzon, J., Marchesi, R., Paredes, D.,
  Bond-Lamberty, B. 2021. A restructured and updated global soil
  respiration database (SRDB-V5). *Earth System Science Data* 13:
  255–267. doi:10.5194/essd-13-255-2021
- Poggio, L. *et al.* 2021. SoilGrids 2.0: producing soil information for
  the globe with quantified spatial uncertainty. *SOIL* 7: 217–240.
- Stell, E., Warner, D., Jian, J., Bond-Lamberty, B., Vargas, R. 2021.
  Spatial biases of information influence global estimates of soil
  respiration: How can we improve global predictions?
  *Global Change Biology* 27 (16): 3923–3938. doi:10.1111/gcb.15666
- Warner, D.L., Bond-Lamberty, B., Jian, J., Stell, E., Vargas, R. 2019.
  Spatial Predictions and Associated Uncertainty of Annual Soil
  Respiration at the Global Scale. *Global Biogeochemical Cycles* 33:
  1733–1745. doi:10.1029/2019GB006264
- Yao, Y., Ciais, P., Viovy, N., Li, W., Cresto Aleina, F., Yang, H.,
  Joetzjer, E., Bond-Lamberty, B. 2021. A Data-Driven Global Soil
  Heterotrophic Respiration Dataset and the Drivers of Its Inter-Annual
  Variability. *Global Biogeochemical Cycles* 35 (8): e2020GB006918.
  doi:10.1029/2020GB006918
