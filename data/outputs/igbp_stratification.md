# IGBP-stratified F (climate-only) Asia → US transfer

*Built 2026-05-05 on branch `claude/item-1-modis` as the **IGBP fallback** authorised by the user after Item 1's pre-flight failed (NPP / LST_day / LST_night placeholders). The MODIS landcover raster IS real; this analysis uses it.*

## What this answers

Run B asked: does within-class stratification rescue cross-
continental Rs transfer? Run B used Köppen-Geiger climate zones
(computable without MODIS) and found within-zone transfer was
*worse* than the cross-zone baseline. The IGBP-stratified test
is the analogous experiment using **land-cover classes** instead
of climate zones — addressing the original question whether the
land-use confound (suspected from the clay-Rs sign-flip in
Section 4 of the paper) is what breaks transfer.

## Bucket definitions (IGBP top-level)

| bucket | IGBP codes | semantics |
|---|---|---|
| forest    | 1, 2, 3, 4, 5 | evergreen/deciduous/mixed forest |
| shrubland | 6, 7         | closed / open shrubland |
| savanna   | 8, 9         | woody / open savanna |
| grassland | 10           | grassland |
| wetland   | 11           | permanent wetland |
| cropland  | 12, 14       | cropland + cropland-natural mosaic |
| barren    | 16           | barren / sparsely vegetated |
| other     | 13, 15, 17, NaN | urban / snow-ice / water / unsampled |

## Site counts

| bucket | Asia | US |
|---|---:|---:|
| forest | 188 | 83 |
| shrubland | 1 | 6 |
| savanna | 147 | 86 |
| grassland | 83 | 34 |
| wetland | 2 | 2 |
| cropland | 109 | 36 |
| barren | 8 | 3 |
| other | 77 | 24 |

## Per-biome transfer (F, 8 bioclim, 1000-iter bootstrap CI)

| biome | n_Asia | n_US | Transfer R² | 95% CI | Excludes 0? | Spearman ρ |
|---|---:|---:|---:|---|---|---:|
| forest | 187 | 82 | -0.265 | (-0.578, -0.058) | **yes** | +0.067 |
| shrubland | 1 | 6 | — | — | — | (skipped: insufficient sites (n_asia=1, n_us=6)) |
| savanna | 146 | 86 | -0.214 | (-0.724, +0.104) | no | +0.248 |
| grassland | 83 | 34 | +0.275 | (-0.060, +0.474) | no | +0.482 |
| wetland | 2 | 2 | — | — | — | (skipped: insufficient sites (n_asia=2, n_us=2)) |
| cropland | 108 | 36 | -0.143 | (-0.472, +0.067) | no | -0.065 |
| barren | 8 | 3 | — | — | — | (skipped: insufficient sites (n_asia=8, n_us=3)) |

**Cross-biome F baseline** (whole-Asia → whole-US, no stratification): R² = +0.127, CI = (+0.020, +0.212). This is the same number reported in Run A's bootstrap_ci.json (re-confirmed on this branch).

## How to read

Two questions per row:

1. **Does within-biome transfer beat the cross-biome baseline?** A
   biome where land-use confounding masks the cross-region signal
   should outperform the cross-biome F baseline once that biome is
   isolated (homogeneous sub-models).

2. **Does the within-biome 95% CI exclude zero?** A biome with a
   positive point estimate but a CI spanning zero has not
   established significant transfer.

## Caveat about *F* vs *F+NPP* and Full+MODIS

This analysis trains the *F* configuration only — climate features
alone. It does not test whether NPP-augmented (F+NPP) or full-
feature (Full+MODIS) models would have within-biome transfer that
improves on the cross-biome baseline, because three of the four
MODIS rasters needed for those configurations are 2-byte placeholders
on this branch (see `RUN_ITEM_1_BLOCKERS.md`). Once real NPP and
LST rasters are pushed, the F+NPP-stratified and Full+MODIS-
stratified versions of this analysis become a one-script run.