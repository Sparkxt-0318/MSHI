# Adversarial Q&A — judge rehearsal

*15 anticipated hostile questions and the rehearsed answers. Tone:
confident, not defensive. Each answer is 2-4 sentences and ends with
a forward-looking pivot where appropriate.*

## Methodology challenges

### Q1.  Why is your transfer R² so low? Most papers report R² > 0.4.
The numbers you've seen are within-sample R² — published continental Rs
papers (Hashimoto 2015, Warner 2019, Yao 2021, Stell 2021) report
Monte-Carlo CIs on the global Pg C yr⁻¹ sum, not held-out
cross-continental site-level R². Our R² = +0.127 with a bootstrap CI
that excludes zero is the first such number in the literature. The
test is harder, and small numbers on a hard test are still informative.

### Q2.  Why didn't you include MODIS NPP — every published Rs upscaling does.
We agree, and it's the next thing we add. The MOD17A3HGF export is
queued through Google Earth Engine; it didn't make this overnight run
because the GEE export takes ~30 minutes and our pipeline ran in a
non-interactive environment without GEE auth. The architecture already
registers the NPP feature; once the raster lands the F+NPP and
Full+MODIS configurations run by re-executing one script.

### Q3.  Have you actually measured this with your sensor?
Not yet. The published EAB work establishes the electrochemistry
under controlled conditions; the co-located biosensor + chamber-Rs
field deployment is the next phase of the project, with two SRDB-listed
sites identified and instrument prep complete. The MSHI-Geo paper
characterises the gap that the field deployment fills, so the two
threads converge naturally on submission.

### Q4.  Couldn't this just be that your model is bad? Try a deeper XGBoost.
We tested six configurations spanning depth 2 to 6, regularisation
λ from 1 to 8, and feature subsets from 8 to 20. Sweep results are
in `data/outputs/sweep_results.json`. Heavier regularisation moves
transfer R² from −0.031 to +0.020 — still indistinguishable from
zero — by shrinking soil-feature contributions to nearly zero.
That's the same fix the climate-only model achieves explicitly.
The model isn't bad; the soil-feature signal is regional.

### Q5.  Why predict respiration at all if soil features don't help?
The negative result IS the contribution. Saying "soil features at this
scale do not improve cross-continental Rs prediction" is a publishable
finding because it constrains the search space for future improvements
and identifies the resolution at which ground-truth measurement actually
adds information. Climate alone gets R² = +0.127, and that's the
defensible upscaling baseline.

## Novelty challenges

### Q6.  What's novel about your work vs Hashimoto/Warner/Yao?
Two things. First, the cross-continental held-out test — every prior
study evaluates within-sample. Second, the explicit characterisation
of the within- vs across-region performance gap, which we localise to
specific features (clay correlates +0.30 with Rs in Asia, −0.05 in US).
The paper draft makes both contributions explicit and cites all four
prior studies for context.

### Q7.  Why is your CV R² negative? That looks like a broken model.
5° spatial-block CV at our sample size (615 Asia sites across all of
Asia) forces every fold to extrapolate to a different climate-biome
combination from anything in the remaining training set. That's by
design: it's a deliberately conservative test. Random-fold CV on the
same data yields R² ≈ +0.09 (in-distribution fit ceiling, also
reported), and held-out US transfer is +0.127 — both positive and
non-trivial.

### Q8.  How do you justify cross-continental testing with only n_us = 272?
The 95 % bootstrap CI on transfer R² uses 2 000 iterations and
correctly characterises the sampling distribution at this n. F's
CI excludes zero (+0.019, +0.216); B's CI includes zero
(−0.141, +0.146). Both numbers correctly reflect the uncertainty
attributable to the small US sample. n = 272 is what the SRDB+COSORE
record allows in CONUS — it's not a choice we made, it's the data
that exists.

## Robustness challenges

### Q9.  What if SRDB Asian sites are biased toward a few studies?
SRDB v5 is the canonical literature-derived compilation (Jian 2021)
and shares this concern with every other published Rs upscaling
model. Stell 2021 explicitly characterises SRDB's "still biased
toward northern latitudes and temperate zones" sampling pattern as a
source of model uncertainty. Our work inherits that concern; the
honest mitigation is the dual-region SHAP analysis showing that the
features driving transfer are climate, not study-author-specific
signals.

### Q10.  Have you done leave-one-study-out sensitivity analysis?
Not yet — that's a planned robustness check for the ESSD revision.
The Round B Köppen-stratification result lowers the prior on
study-id confound being a major issue: if individual studies were
driving transfer, removing them would change Köppen results, but the
within-zone failure is uniform across both qualifying climate zones.
The leave-one-study-out will go in the paper supplement.

### Q11.  Why Köppen instead of IGBP biomes?
Substitute, not preference. The IGBP-stratified test was the
original plan; the MOD12Q1 land-cover raster is queued for GEE
export. Köppen is computable without MODIS — directly from the
WorldClim bioclim variables we already have — so it provides a
related stratification while the IGBP raster lands. The paper
draft is explicit about this substitution.

### Q12.  Within-zone results were worse than baseline — doesn't that hurt your claim?
On the contrary. It strengthens it. The cross-zone transfer R² of
+0.127 is being carried by the cross-zone precipitation gradient,
which the SHAP analysis already identified as the only stable
cross-region signal. If stratifying could improve transfer, our
claim that "soil-driven Rs variability needs ground truth" would be
weaker. The Köppen result establishes that climate-zone slicing of
gridded data does not recover transfer.

## Project / pitch challenges

### Q13.  Why publish before adding NPP?
Because the MODIS-pending question is "does NPP rescue the
soil-features failure" — and the answer matters whichever way it
goes. If NPP rescues, the upscaling pipeline gains a working
ground-truth proxy and the paper version 2 becomes more positive.
If it doesn't, the structural argument for in-situ biosensor
networks gets sharper. The paper draft frames both outcomes; the
ESSD submission is structured to accept the NPP results as a
revision rather than blocking the initial submission.

### Q14.  What's the path to deployment for your sensor?
Three stages. (1) Co-located pilot at two SRDB-listed sites with
chamber Rs measurement running in parallel — establishes the EAB
current vs chamber-Rs calibration empirically. (2) Multi-site
network of low-cost EAB sensors at 10-20 sites spanning Köppen
zones C and D where our gridded model fails — populates the
ground-truth layer the upscaling model needs. (3) Open data
publication and integration into the next SRDB version. Stage 1
hardware exists; stages 2-3 are the funding ask.

### Q15.  What would falsify your central claim?
The central claim is: "soil-driven Rs variability at continental
scale requires ground-truth measurement that current gridded
products cannot supply." Three results would falsify it:
(a) IGBP-stratified models that recover cross-continental transfer
without in-situ data; (b) MODIS NPP plus soil features yielding
transfer R² > 0.4 with bootstrap CI safely above zero; or
(c) successful Asia → US transfer of a soil-feature-only model
in some other study. None has yet appeared, and our prior — based
on the Köppen result and the dual-region SHAP — is that
(a) and (b) will not turn out that way. (c) is what we're
actively watching the literature for.
