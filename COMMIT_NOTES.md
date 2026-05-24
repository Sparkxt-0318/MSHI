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

---

## Phase 2A — methodology_evolution_panel_v2 verification

**No regen needed.** All values on the existing
`data/outputs/methodology_evolution_panel_v2.png` already match the
source-of-truth list. Verified by visually reading the rendered image:

| Sub-panel | Image text | Source-of-truth | Match? |
|---|---|---|---|
| F (climate-only) | "Transfer R² = +0.127, CI (+0.019, +0.216) · statistically significant" | +0.127, CI (+0.019, +0.216) | ✓ |
| F+NPP | "Transfer R² = +0.145, CI (+0.026, +0.241) · best of any config" | +0.145, CI (+0.026, +0.241) | ✓ |
| Full+MODIS | "Transfer R² = +0.072, CI (-0.084, +0.189) · CV jumps but transfer CI spans 0" | +0.072, CI (-0.084, +0.189) | ✓ |
| Köppen C | "Net trans F = -0.336, CI (-3.06, +0.04) · spans 0" | -0.336 | ✓ |
| Köppen D | "Net trans F = -0.199, CI (-0.392, -0.061) · significantly worse" | -0.199 | ✓ |

Sidebar "Item 1 take-aways" text also references the +0.145 F+NPP value
and the "Full+MODIS rescues CV but not transfer" narrative — all
consistent with the data.

No script run, no file modified.

## Phase 2B — framing2_comparison_panel regenerated

Script: `scripts/regen_framing2_panel.py` (new).

The previous middle-panel title read `transfer R² = +0.020` (Run-A
B_heavier_reg). The user asked for `transfer R² = +0.072` (Full+MODIS)
and a softening of "overfits Asia" → "more features hurt" since the
Full+MODIS CI spans zero.

### Files written

| File | Old title (middle panel) | New title (middle panel) |
|---|---|---|
| `data/outputs/framing2_comparison_panel.png` | "Climate + soil features (overfits Asia: transfer R² = +0.020)" | "Climate + soil features (more features hurt: transfer R² = +0.072)" |
| `data/outputs/framing2_comparison_panel_legacy.png` | — | Renamed copy of the previous panel |

### Data + framing changes

The previous panel used three 5 km anomaly grids:

- Left  : F anomaly  = exp(F_pred) / exp(5-bio baseline pred)
- Middle: B anomaly  = exp(B_pred) / exp(5-bio baseline pred)
- Right : B − F      (soil-feature contribution)

The 5 km grid + 5-bio baseline parquets aren't on disk on this branch
(see Phase 1 caveat). The new panel uses the 0.5° atlas_lookup data:

- Left  : F anomaly  = exp(F_pred) / exp(F's own median log_rs)
  — same conceptual framing (anomaly ratio centered near 1.0), with the
  denominator switched from a 5-bio model to a global F median. This
  preserves the visual scale but isn't strictly identical to the old left
  panel; the anomaly map shows F's spatial deviation from its own
  central tendency. Recorded as a deviation in this notes file.
- Middle: Full+MODIS anomaly = exp(Full+MODIS_pred) / exp(8-bio baseline pred)
  — comes from `atlas_lookup.json cells[i].fullmodis.anomaly` directly.
- Right : Full+MODIS anomaly − F anomaly (same cell, same scale).

The left-panel framing change is the only methodological deviation;
the R² annotations in the title are unaffected (they come from the
metrics JSON regardless of the visualisation choice).

### Gate 2 results

- ✓ methodology_evolution_panel_v2 confirmed correct — no regen
- ✓ framing2 middle-panel title now reads `transfer R² = +0.072`
- ✓ "+0.020" appears nowhere in the new framing2 panel — verified visually
- ✓ Panel dimensions: 2880 × 1120 (matches legacy)
- ✓ Same RdBu_r colormap, same 3-panel layout, same external horizontal
  colorbars, same suptitle
- ⚠ Smaller PNG size (330 KB vs 3.0 MB) — 0.5° vs 5 km resolution
