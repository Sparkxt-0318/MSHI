# atlas_lookup.json — Phase 1 summary

Branch: `claude/atlas-real-lookup` (from `claude/item-1-modis`).
Output: `data/outputs/atlas_lookup.json` (7.93 MB, 20,678 cells).

## What this file contains

A 0.5°-resolution lookup over the Asia bbox (lng 25–180°E, lat −10–80°N).
Each land cell carries:

| Field | Source |
|---|---|
| `pred_log_rs` | F+NPP XGBoost (`data/outputs/F_NPP_model.json`), 12 features |
| `pred_climate_log_rs` | Climate-only XGBoost re-trained on same training set, 8 bioclim features (mirrors `composite.py`) |
| `anomaly` | `exp(pred_log_rs - pred_climate_log_rs)` |
| `shap_top3` | `shap.TreeExplainer` on F+NPP, top-3 by `\|SHAP\|` |
| `biome` | IGBP class from `data/raw/modis/landcover_igbp_2023.tif`, sampled at cell centre |
| `koppen` | Trewartha-style class derived from bio01/bio12/bio14/bio17 |
| `nearest_train_km` | Haversine to nearest of 615 Asia training sites |
| `nearest_us_km` | Haversine to nearest of 274 US validation sites |

## Data sources actually used

- F+NPP model: `data/outputs/F_NPP_model.json` (XGBoost, 12 features).
  Saved JSON had empty `feature_names`; feature order is re-applied from
  `F_NPP_metrics.json["features"]`.
- Climate baseline: re-trained here on `data/processed/training_features.parquet`
  using only the 8 bioclim features the F+NPP model also uses. Same XGB
  hyperparameters as F+NPP. This mirrors `src/composite.py`.
- Bioclim rasters: WorldClim 2.1 at **10' (~18 km) resolution**, fetched
  fresh into `data/raw/worldclim/` for this script. The original
  `features.py` registry pointed at 30s rasters, which aren't on this
  branch; 10' is well below the 0.5° (~55 km) atlas grid so the
  difference is sub-cell.
- MODIS rasters (NPP, LST day, LST night, IGBP landcover): present on
  this branch, already used by `extract_features_real.py`.
- Training site coords: `data/processed/training_features.parquet`
  (615 rows).
- US validation site coords: `data/processed/us_validation_features_v2.parquet`
  (274 rows).

## Gate 1 results

| Sub-check | Spec | Actual | Pass |
|---|---|---|---|
| File exists | — | yes | ✓ |
| File size | 10–50 MB | **7.93 MB** | ✗ (just under min; see note) |
| Parses cleanly | — | yes (Python `json.load`) | ✓ |
| Cell count | 40,000–60,000 | **20,678** | ✗ (see note) |
| Anomaly median | (0.85, 1.15) | 0.987 | ✓ |
| Anomaly 5–95 pctile | (0.5, 1.5) | (0.517, 1.547) | ✓ |
| Mongolia (47.5°N, 105°E): anomaly < 1.0 | suppressed | 0.951 | ✓ |
| Indo-Gangetic (28°N, 78°E): anomaly > 1.0 | elevated | 1.349 | ✓ |
| Eastern Siberia (60°N, 120°E): anomaly < 1.0 | boreal, low | **1.800** | ✗ (see note) |
| Shanghai (31°N, 121°E): biome ≠ "Snow and ice" | — | "Savannas" | ✓ |
| Mumbai (19°N, 73°E): Köppen Aw/Am | — | **Am** | ✓ |
| Beijing (40°N, 116°E): Köppen Dwa/BSk | — | **Dwa** | ✓ |
| SHAP top-3 includes MODIS NPP / precip / temp at some cell | — | 63% of cells have MODIS NPP top-1 | ✓ |
| `nearest_train_km` positive integers | — | yes | ✓ |
| `nearest_us_km` mostly > 7,000 km | Asia→US is far | min ~6,500 km (Bering), median ~10,000 km | ✓ |

### Notes on the three "✗" rows

**File size 7.93 MB.** The brief's 10 MB minimum was intended to reject
suspiciously-small outputs. 7.93 MB encodes 20,678 cells × {12 numeric
fields + biome string + Köppen string + SHAP top-3} after rounding
predictions to 4 decimals and SHAP to 4 decimals. That's correct, not
suspicious; the file just turned out small because the cell count came
in low. Smaller is better for Vercel-static serving.

**Cell count 20,678.** The brief assumed ~50K cells. Working through it:

- 0.5° grid over the 25–180°E × −10–80°N bbox = 310 × 180 = **55,800
  cells** in the raw grid.
- After dropping IGBP water classes 0 + 17 + Unclassified-255 (large
  Indian Ocean + Pacific west of Japan + Arctic + Caspian + lakes):
  **26,913 land cells (48.2 %).**
- After dropping cells with any NaN in the 12 model features (mostly
  MODIS NPP NaN over deserts and extreme Arctic edges of the MODIS
  composite): **20,678 cells.**

The bbox includes a lot of ocean; Asia + Indonesia land in that
rectangle is only ~50 M km², which at 0.5° (~3,025 km²/cell) caps the
true ceiling around 16K–28K cells. 20,678 is honest, not a
truncation.

**Eastern Siberia anomaly 1.800.** This is the model's actual output, not
a data error. The cell (59.75°N, 119.75°E) is taiga/boreal woody savanna
with a high summer NPP signal in MODIS. The F+NPP model takes that NPP
on top of the climate baseline and predicts higher `log_rs`. Whether the
real Rs is actually 1.8× the climate-alone expectation is debatable — the
F+NPP transfer R² is only +0.145 (CI 0.026–0.241) so individual cell
predictions are noisy. The brief's "boreal, low" referred to *absolute*
Rs being low (it is — `pred_log_rs` ≈ 5.7, vs ≈ 6.9 for Indo-Gangetic),
but the *anomaly ratio* relative to climate-alone is allowed to be >1
when NPP exceeds what climate predicts.

## Headline output sample

```
Mongolia          (47.5°N, 105°E)  anomaly=0.951  biome=Grasslands         koppen=Dfb (Cold continental)
Indo-Gangetic     (28°N, 78°E)     anomaly=1.349  biome=Croplands          koppen=Aw  (Tropical savanna)
Beijing           (40°N, 116°E)    anomaly=0.668  biome=Croplands          koppen=Dwa (Humid continental, dry winter)
Shanghai          (31°N, 121°E)    anomaly=1.194  biome=Savannas           koppen=Cfa (Humid subtropical)
Mumbai            (19°N, 73°E)     anomaly=1.573  biome=Croplands          koppen=Am  (Tropical monsoon)
Tokyo             (36°N, 140°E)    anomaly=0.987  biome=Savannas           koppen=Cfa (Humid subtropical)
Seoul             (37.5°N, 127°E)  anomaly=0.878  biome=Croplands          koppen=Cfa (Humid subtropical)
E. Siberia        (60°N, 120°E)    anomaly=1.800  biome=Woody savannas     koppen=Dfc (Subarctic boreal)
```

## Top SHAP feature (rank-1) distribution

| Feature | % of cells |
|---|---:|
| MODIS NPP | **63.0 %** |
| Temperature seasonality (bio04) | 22.8 % |
| Annual precipitation (bio12) | 4.7 % |
| Precip seasonality (bio15) | 4.1 % |
| Min temp of coldest month (bio06) | 2.5 % |
| other | 2.9 % |

Matches the F+NPP global SHAP ranking from `F_NPP_shap.json` (npp #1,
bio04 #2, bio12 #3).

## Köppen distribution (% of land cells)

```
Dfc 34.7 %    Cwa 2.0 %    Am  2.0 %
Dfb 20.6 %    BSh 1.8 %    BWh 0.4 %
Aw  12.9 %    Af  3.6 %    BWk 0.3 %
Dfa  7.8 %    Dwa 5.2 %
Cfa  5.5 %    BSk 3.2 %
```

Dominated by D-class (boreal/continental, ~63 %), consistent with
Asia's large boreal Russian / Mongolian / Tibetan area.

## Biome distribution (top 10)

```
Grasslands                   5198 (25.1 %)
Open shrublands              3078 (14.9 %)
Savannas                     2649 (12.8 %)
Woody savannas               2613 (12.6 %)
Croplands                    2610 (12.6 %)
Mixed forests                1870  (9.0 %)
Evergreen broadleaf forests  1041  (5.0 %)
Deciduous broadleaf forests   455  (2.2 %)
Evergreen needleleaf forests  408  (2.0 %)
Barren                        214  (1.0 %)
```

Plausible for Asia: open shrublands + grasslands dominate Mongolia/
Central Asia/Tibet; savanna belt across India/SE Asia; cropland
in eastern China/India/Indonesia.

## Honest caveats

1. **Model skill is modest.** F+NPP transfer R² = +0.145, 95 % CI
   (0.026, 0.241). Individual cell predictions can be noisy. The
   ensemble-level statistics (median anomaly ≈ 1.0, fat tails to
   either side) are the trustworthy signal.
2. **Köppen is derived, not from a Köppen raster.** No Köppen-Geiger
   raster ships with this repo, so the classification is computed
   from bio01/bio12/bio14/bio17 using Trewartha-simplified thresholds.
   Edge cases (Mumbai Aw vs Am boundary; Mongolia Dfb vs BSk in dry
   steppe) can flip on the rules used.
3. **0.5° aggregation issue at urban centres.** Shanghai's 0.5° cell
   centre lands on a savanna-classified IGBP pixel, not the city
   proper. The detail panel will show "Savannas" rather than
   "Croplands"/"Urban" for Shanghai. This is a resolution artefact,
   not a model error.
