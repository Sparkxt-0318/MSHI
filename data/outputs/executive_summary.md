# MSHI-Geo — executive summary

*[Author Name]   ·   [School]   ·   Genius Olympiad 2026*

**Problem.** Soil respiration is the second-largest carbon flux on
Earth (~91 Pg C yr⁻¹), but no published continental Rs upscaling
model has been tested for held-out cross-continental transfer — the
decision-relevant generalisation question.

**Approach.** I built an XGBoost upscaling pipeline using 615 Asian
soil-respiration sites (SRDB v5 + COSORE) for training and a held-out
274-site CONUS subset for validation. Features draw from WorldClim 2.1
bioclimatic variables and SoilGrids 2.0 5–15 cm topsoil layers. Six
hyperparameter and feature-set configurations were tested; per-region
SHAP and Köppen-Geiger climate-zone stratification probe the mechanism
behind whatever transfer or failure shows up. Statistical significance
on transfer R² is established with 2,000-iteration bootstrap CIs on
the held-out CONUS sample.

**Headline finding.** A model restricted to 8 WorldClim climate
features transfers Asia → CONUS at **R² = +0.127 (95 % bootstrap CI
+0.019 to +0.216, n = 272)** — statistically significant. Adding 8
SoilGrids texture features collapses transfer to R² = +0.020
(CI −0.141 to +0.146, indistinguishable from zero). To the best of
my knowledge this is the first published held-out cross-continental
site-level transfer R² for any continental Rs model.

**Mechanism.** Per-region SHAP shows the Asia and CONUS models share
only one top driver — annual precipitation (bio12). The Asia clay-Rs
correlation r = +0.302 flips to r = −0.048 in CONUS, so a model
trained on Asia learns "more clay → more Rs" and fails by construction
on CONUS. Köppen-Geiger climate-zone stratification was tested as a
remedy and *worsened* transfer in both qualifying zones, identifying
the cross-zone precipitation gradient as the only generalisable signal.

**Implication.** Two of three components of the standard upscaling
recipe — gridded climate, gridded soil, gridded vegetation — are
themselves modelled, not measured. Continental Rs maps that
under-represent soil-driven variability cannot be fixed by adding
features from the same generation of remote products. The gap is the
absence of dense in-situ measurement at the centimetre scale where
soil heterogeneity actually lives — exactly what low-cost
electrochemically-active-biofilm (EAB) biosensor networks could close.

**Status.** Published EAB sensor work is the first scale of this
project; the MSHI-Geo manuscript is queued for *Earth System Science
Data*; this executive summary, the 12-slide pitch deck, the 36 × 24 in
poster, the dual-region SHAP and methodology evolution figures, and
the full reproducible code pipeline are all on the
`claude/round-c-deliverables` branch of the repository.
