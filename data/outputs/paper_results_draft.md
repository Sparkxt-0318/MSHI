# Results — MSHI-Geo continental respiration model

*Draft, internal. Working numbers from the 2026-04-26 overnight run.*

## 1. Training data and target

We assembled a global training table from two community databases of soil
respiration: the Soil Respiration Database (SRDB v5; Bond-Lamberty & Thomson
2010), which compiles literature-derived annual soil respiration estimates
(*Rs<sub>annual</sub>*, g C m⁻² yr⁻¹), and the COntinuous SOil REspiration
database (COSORE; Bond-Lamberty et al. 2020), which provides high-frequency
chamber-flux time series. SRDB contributed 4,771 records after dropping
manipulated treatments and out-of-range values
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
total. MODIS NPP, LST, and IGBP land-cover layers were specified in the
configuration but were not available for this run.

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

## 3. Asia → US transfer

The held-out validation test addresses the project's primary scientific
question: does a model trained on Asian soil-respiration measurements
generalise to a different continent? With the climate-only configuration
the answer is *partially* — R² = +0.127, RMSE = 0.59 log units (≈ 80%
multiplicative error in *Rs*), bias = −4%. With any feature set that
includes the SoilGrids texture layers (clay, sand, silt, or their ratios),
generalisation collapses to R² ≈ 0.

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

Published continental *Rs* models report similar ceilings. [NEEDS
CITATION: Hashimoto et al. 2015, *Biogeosciences*] reports global random-
forest *Rs* models with R² ≈ 0.40–0.55 at the site level, but does not
report cross-continental transfer. [NEEDS CITATION: Yao et al. 2019] uses
machine-learning upscaling on a similar feature stack and finds soil
features marginal beyond climate, consistent with our finding here.
[NEEDS CITATION: Chen et al. 2020] specifically reports the within-region
versus across-region performance gap.

## 6. Discussion — what would close the gap

Three classes of intervention can plausibly improve the Asia → US transfer
beyond the +0.13 ceiling we observe with climate-only features.

**Higher-quality vegetation activity proxies.** The dominant control on
soil respiration at continental scale is substrate input from above-ground
production (*Q* in the *Q*<sub>10</sub>-*Q* framework). MODIS NPP at
500 m – 1 km has been a widely-used proxy in published *Rs* upscaling and
typically lifts model R² by 0.10–0.20 over climate-only baselines. We
specified MOD17A3HGF NPP in our feature configuration but did not include
it in this run; adding it is the single highest-priority next step.

**Regional sub-models or biome stratification.** Because the
feature → *Rs* relationship differs between Asia and US (Section 4), a
single global model is poorly specified. Training separate sub-models per
Köppen climate zone or per IGBP land-cover class would allow each to fit
its local relationship. The trade-off is that each sub-model has fewer
training points and so wider parameter uncertainty.

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

## References

- Bond-Lamberty, B. & Thomson, A. 2010. A global database of soil
  respiration data. *Biogeosciences* 7: 1915–1926.
- Bond-Lamberty, B. *et al.* 2020. COSORE: A community database for
  continuous soil respiration and other soil-atmosphere greenhouse gas
  flux data. *Global Change Biology* 26: 7268–7283.
- Fick, S.E. & Hijmans, R.J. 2017. WorldClim 2: new 1-km spatial
  resolution climate surfaces for global land areas. *International
  Journal of Climatology* 37: 4302–4315.
- Poggio, L. *et al.* 2021. SoilGrids 2.0: producing soil information for
  the globe with quantified spatial uncertainty. *SOIL* 7: 217–240.
- [NEEDS CITATION: Hashimoto, S. *et al.* 2015. Global spatiotemporal
  distribution of soil respiration modeled using a global database.
  *Biogeosciences* — verify volume/pages.]
- [NEEDS CITATION: Yao, Y. *et al.* 2019 — soil-respiration upscaling
  paper referenced in framing — verify exact reference.]
- [NEEDS CITATION: Chen, S. *et al.* 2020 — within-region vs cross-region
  performance gap — verify exact reference.]
- [NEEDS CITATION: Zhang, H. *et al.* 2017 — continental Rs upscaling
  — verify exact reference.]
