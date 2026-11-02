# Köppen-Geiger climate-zone stratification

*Substitute for IGBP biome stratification while MODIS land-cover is blocked. See `RUN_B_BLOCKERS.md`.*

Köppen top-level classes computed from WorldClim bio05, bio06, bio12, bio14. Per zone with ≥80 Asia training sites and ≥30 US validation sites, the F (climate-only, 8 bioclim features) model is trained on the Asia subset and tested on the US subset.

## Class counts

| Class | Asia | US | Description |
|---|---:|---:|---|
| A | 57 | 0 | Tropical (coldest month ≥ 18 °C) |
| B | 51 | 24 | Arid (heuristic: P_ann < 400 AND driest-month < 30 mm) |
| C | 247 | 89 | Temperate (coldest month −3…18 °C; warmest ≥ 10 °C) |
| D | 244 | 159 | Continental (coldest month < −3 °C; warmest ≥ 10 °C) |
| E | 1 | 0 | Polar (warmest month < 10 °C) |

## Per-zone transfer results

| Zone | n_Asia | n_US | Transfer R² | 95% CI | Excludes 0? | Spearman ρ |
|---|---:|---:|---:|---|---|---:|
| A | — | — | — | — | — | (skipped: insufficient sites (n_asia=57, n_us=0)) |
| B | — | — | — | — | — | (skipped: insufficient sites (n_asia=51, n_us=24)) |
| C | 247 | 89 | -0.336 | (-1.060, +0.035) | no | +0.207 |
| D | 244 | 159 | -0.199 | (-0.392, -0.061) | **yes** | -0.045 |
| E | — | — | — | — | — | (skipped: insufficient sites (n_asia=1, n_us=0)) |

**Cross-zone F baseline** (whole-Asia → whole-US, no stratification): R² = +0.127, CI = (+0.020, +0.212).

## Reading

Two analytical questions for each Köppen zone:

1. **Does within-zone transfer beat the cross-zone baseline?** A zone where the cross-continent feature → Rs relationship is more stable should outperform the cross-zone F model (which has to average over all zones).

2. **Does within-zone transfer's 95% CI exclude zero?** This is the honest sufficient-evidence test. A zone where the CI includes zero did not establish significant transfer, even if the point estimate is positive.

## Caveat

Köppen zones aggregate over land-cover, which the IGBP scheme would have separated. A `forest` and a `cropland` site can fall in the same Köppen zone yet have very different soil-respiration relationships. When MODIS land-cover lands, the IGBP-stratified analysis will likely tighten the within-class results further by removing the land-use confound this analysis cannot.