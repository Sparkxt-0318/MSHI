# Atlas figure regen 2026 — commit notes

Branch: `claude/atlas-figure-regen-2026`
Parent: `claude/lucid-lovelace-f3D5H` (latest atlas work branch; carries
the Full+MODIS model and the atlas_lookup pipeline)

---

## Phase 0 — source-of-truth verification

All five headline R² values were checked against the published artefacts
in `data/outputs/`. The user-supplied source-of-truth list matches the
repo files within rounding, with one minor footnote.

| Config | User value | Repo file | Repo raw value | Match? |
|---|---|---|---|---|
| F R² | +0.127 | `bootstrap_ci.json["F_climate_only"]["point_r2"]` | 0.127 | ✓ |
| F CI low | +0.019 | `bootstrap_ci.json["F_climate_only"]["ci_low"]` | 0.0193 | ✓ |
| F CI high | +0.216 | `bootstrap_ci.json["F_climate_only"]["ci_high"]` | 0.216 | ✓ |
| F+NPP R² | +0.145 | `F_NPP_metrics.json transfer.r2` | 0.1447 | ✓ |
| F+NPP CI low | +0.026 | `F_NPP_metrics.json transfer.ci_low` | 0.0258 | ✓ |
| F+NPP CI high | +0.241 | `F_NPP_metrics.json transfer.ci_high` | 0.2413 | ✓ |
| F+NPP n_train | 463 | `F_NPP_metrics.json n_train` | 463 | ✓ |
| F+NPP n_us | 223 | `F_NPP_metrics.json n_us` | 223 | ✓ |
| Full+MODIS R² | +0.072 | `Full_MODIS_metrics.json transfer.r2` | 0.0724 | ✓ |
| Full+MODIS CI low | -0.084 | `Full_MODIS_metrics.json transfer.ci_low` | -0.0840 | ✓ |
| Full+MODIS CI high | +0.189 | `Full_MODIS_metrics.json transfer.ci_high` | 0.1886 | ✓ |
| Full+MODIS n_train | 463 | `Full_MODIS_metrics.json n_train` | 463 | ✓ |
| Full+MODIS n_us | 223 | `Full_MODIS_metrics.json n_us` | 223 | ✓ |
| Köppen C R² | -0.336 | `koppen_stratification.json["C"]["transfer_r2"]` | -0.3362 | ✓ |
| Köppen D R² | -0.199 | `koppen_stratification.json["D"]["transfer_r2"]` | -0.1986 | ✓ |
| Asia n (sweep v2) | 615 | `sweep_results_v2.json asia_n` | 615 | ✓ |
| US n (sweep v2) | 274 | `sweep_results_v2.json us_n` | 274 | ✓ |

**Minor footnote — F's bootstrap CI.** Two files report bootstrap CIs
for F. `bootstrap_ci.json` gives (+0.0193, +0.216), which matches the
user's source-of-truth (+0.019, +0.216). The koppen stratification file
re-bootstrapped F as an internal baseline with a different rng path and
got (+0.0202, +0.2123). Treating `bootstrap_ci.json` as canonical per
the user's stated value. The discrepancy is in the third decimal place
and reflects bootstrap sampling noise; both files agree on point R²
(+0.127). No source-of-truth conflict.

### Data inventory

| Artefact | Present? | Notes |
|---|---|---|
| `data/outputs/F_NPP_model.json` | ✓ | XGBoost JSON, 12 features |
| `data/outputs/Full_MODIS_model.json` | ✓ | XGBoost JSON, 34 features |
| `data/outputs/F_NPP_metrics.json` | ✓ | Source of truth for F+NPP |
| `data/outputs/Full_MODIS_metrics.json` | ✓ | Source of truth for Full+MODIS |
| `data/outputs/sweep_results_v2.json` | ✓ | All 8 configs aggregated |
| `data/outputs/koppen_stratification.json` | ✓ | C/D subset R² |
| `data/outputs/bootstrap_ci.json` | ✓ | F + B Run-A bootstrap CIs |
| `data/processed/training_features_v2.parquet` | ✓ | 615 Asia rows × 32 cols |
| `data/processed/us_validation_features_v2.parquet` | ✓ | 274 US rows × 32 cols |
| `data/processed/asia_predictions_F_NPP.parquet` | ✓ | 5.58 M cells at 5 km |
| `data/processed/hero_climate_npp_asia_anomaly.parquet` | ✓ | F+NPP 5 km anomaly |
| `data/processed/asia_grid_5km.parquet` | **✗** | Full grid features — never committed; intermediate |
| `data/processed/asia_grid_5km_v2.parquet` | **✗** | Same, post-MODIS-sampling intermediate |
| `data/outputs/atlas_lookup.json` | ✓ | 0.5° lookup w/ Full+MODIS anomaly per cell |
| WorldClim 8-bioclim rasters | **✗** | Not on this branch (used at training; gone) |
| SoilGrids 8 rasters | **✗** | Not on this branch |
| MODIS 4 rasters | ✓ | `data/raw/modis/` |

### Phase 1 blocker (resolved)

A 5 km Full+MODIS Asia grid (the natural successor to
`asia_predictions_F_NPP.parquet`) does **not exist on disk**. Recreating
it would require re-sampling all 34 features over the 5.58 M-cell grid,
which needs WorldClim + SoilGrids rasters that aren't checked in.

The user was asked how to proceed (options: 0.5° render with honest
footer; HALT; or approximate at 5 km using bioclim only). The choice was
**render at 0.5° with the footer labelled accurately**. Phase 1 below
implements that.

---

## Phase 1 — hero_full_features_asia regenerated at 0.5°

Script: `scripts/regen_hero_full_modis.py` (new in this branch).
Driving function: `src.hero_map.render_hero_map` (unchanged).

### Files written

| File | Old footer | New footer | Notes |
|---|---|---|---|
| `data/outputs/hero_full_features_asia.png` | `MODEL XGBoost · resolution ~5 km` `CV R² -0.083  Asia→US R² 0.020` `N(train)=615 N(US)=274` | `MODEL XGBoost · resolution ~55 km` `CV R² 0.079  Asia→US R² 0.072` `N(train)=463 N(US)=223  2026-05-24` | Header subtitle: "FULL+MODIS MODEL". Bold red tagline: "Adds soil structure features — transfer drops; CI spans zero" |
| `data/outputs/hero_full_features_asia.pdf` | (same as png) | (same as png) | |
| `data/outputs/hero_full_features_asia_screen.png` | (same as png) | (same as png) | |
| `data/outputs/hero_full_features_asia_legacy.{png,pdf}` | — | — | Renamed copy of the previous Run-B "B_heavier_reg" hero; preserved for visual diff |
| `data/outputs/hero_full_features_asia_legacy_screen.png` | — | — | Ditto |
| `data/processed/hero_full_features_asia_anomaly.parquet` | — | — | New: 20,678 cell anomaly extracted from `atlas_lookup.json` |

### Resolution caveat

The new hero is at 0.5° / ~55 km (310 × 175 grid, 20,678 land cells).
The previous Run-B hero was at 0.05° / ~5 km. Pixels in the new image
are visibly chunkier — this is honest about the underlying data and
is documented in the footer (`resolution ~55 km`).

If a 5 km Full+MODIS Asia hero is needed in the future, the path is:
1. Re-download WorldClim 8 bioclim rasters + SoilGrids 8 rasters
2. Re-build asia_grid_5km.parquet via `src/extract_features_real.py`
3. Sample MODIS + add IGBP one-hot, the way `item1_c5_hero_fnpp.py` does
4. Predict with `Full_MODIS_model.json` on the 34-feature grid
5. Compute anomaly = exp(Full+MODIS pred) / exp(climate baseline pred)
6. Pass that parquet to `render_hero_map`

No model retraining is needed; only feature extraction at 5 km.

### Gate 1 results

- ✓ Output file footer shows `Asia→US R²  0.072` — verified by reading the rendered PNG
- ✓ The value `0.020` appears nowhere in the new image — verified
- ✓ PNG dimensions: 4906 × 2850 (matches `hero_climate_npp_asia.png`)
- ✓ Same diverging RdBu colormap (uses `src.hero_map.build_diverging_cmap`)
- ✓ Same legend structure / interpretation rows
- ⚠ File sizes smaller (PNG 3.3 MB vs 9.7 MB) because 0.5° grid has fewer
  unique colours per area → better PNG compression. Not a defect.
