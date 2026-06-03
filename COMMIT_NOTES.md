# Atlas global coverage — commit notes

**Branch:** `claude/atlas-global-lookup` (from `main`)
**Task:** Extend the interactive atlas to global land coverage, with all
non-Asia cells flagged as cross-continental transfer predictions.
**Date:** 2026-06-02
**Outcome:** Global MODIS is absent for 69% of land (see `BLOCKERS.md`), so a
truly global build is impossible. After surfacing this, the **honest partial
extension** was approved: predict transfer cells everywhere real MODIS exists
(31% of land), flag them `domain: "transfer"`, and document the MODIS-absent
remainder rather than fabricate it. No feature data fabricated; Asia cells
preserved byte-for-byte (values); no figures or non-atlas artifacts produced.

**Result:** `atlas_lookup.json` → **27,393 cells, 38 MB** = 20,678 Asia
(`domain: "training"`) + **6,715 non-Asia (`domain: "transfer"`)**.

---

## Phase 0 — pipeline + feature-data inventory

### Pipeline
- **Build script:** `scripts/build_atlas_lookup.py` — builds the 0.5° Asia
  grid (`ASIA_BBOX = (25, −10, 180, 80)`), samples features per cell, predicts
  with F+NPP and Full+MODIS + a re-trained climate baseline, computes per-cell
  SHAP top-3, IGBP biome, Köppen, nearest-site distances. Output schema
  `atlas_lookup.v3`: `{grid, models:{fnpp,fullmodis}, cells:[{lat,lon,fnpp,
  fullmodis,biome,koppen,nearest_*_km}]}`.
- **Models load & verified:**
  - `data/outputs/F_NPP_model.json` (XGBoost, 12 features) ✓ loads.
  - `data/outputs/Full_MODIS_model.json` (XGBoost, 34 features) ✓ loads.
  - F+NPP needs `bioclim×8 + npp + lst_day + lst_night + lst_diurnal_range`
    (NO soil). Full+MODIS adds `soilgrids×8 + 4 engineered + 10 IGBP one-hots`.
- **Existing atlas:** `data/outputs/atlas_lookup.json` — 28 MB, **20,678 Asia
  land cells**, schema v3. Tracked in git (force-added past `.gitignore`).

### Feature-layer inventory (verified on disk)
| Layer | On disk? | Geographic extent (verified) |
|---|---|---|
| MODIS NPP / LST day / LST night | partial | bbox lon[-125,180] lat[-39,88], **but data only in Asia/Oceania/US box** — see below |
| MODIS IGBP land cover | partial | bbox global, data only in study footprint (0=water elsewhere) |
| WorldClim bioclim (8) | ✗ → **acquired** | was missing; downloaded global (this run) |
| SoilGrids (8 rasters) | ✗ → **acquired** | never existed as rasters; downloaded global (this run) |

**Key Phase-0 finding (contradicts the brief's premise):** the MODIS rasters
are **not global**. Their bounding box is wide but the valid data is the union
of the Asia and US GEE exports. Measured on the 0.5° grid against a WorldClim
land mask: **MODIS covers only 31.0% of global land (27,813 / 89,773 cells).
South America 0%, Africa 20%, Europe 31%, N. America 35%** (vs Asia 75%,
Oceania 72%). Full breakdown in `BLOCKERS.md`.

---

## Phase 1 — global feature acquisition

### Acquired ✅
| Dataset | Detail | Size | Validation |
|---|---|---|---|
| WorldClim 2.1 bioclim 10′ | bio01/04/05/06/12/14/15/17 → `data/raw/worldclim/wc2.1_10m_bio_*.tif` (matches `build_atlas_lookup.py` paths) | 22 MB | Global; data on all continents. |
| SoilGrids 2.0 5–15cm mean | 8 vars → `data/raw/soilgrids/*_5-15cm_global_0p1.tif` via ISRIC WCS | 13 MB | Units rescaled per `src/features.py`; **medians match training** (phh2o 6.2 vs 5.9, bdod 1.23 vs 1.20, nitrogen 2.3 vs 2.14, soc 28.1 vs 27.5). Real rasters, **not** the Asia-training NN imputation (forbidden globally). |

Manifest: `data/raw/ACQUISITION_MANIFEST.json`. (Rasters live in gitignored
`data/raw/`; the manifest is committed as the checkpoint of record.)

### Missing — BLOCKER ❌
**MODIS NPP / LST / IGBP** cannot be obtained globally:
- GEE (`earthengine-api`) not installed and needs credentials.
- LP DAAC needs Earthdata Login.
- MS Planetary Computer (anonymous) has NPP + LST tiles but **not** MCD12Q1
  land cover; and a client-side 2020–2024 mean of 8-day LST over ~286 global
  tiles (~65k COG reads) is not tractable overnight.

Detail, per-continent coverage, and exact sources attempted: `BLOCKERS.md`.

---

## Decision — HALT (per the brief's own rules)

- The brief's sanctioned reduced fallback (F+NPP-only global, skip Full+MODIS)
  is permitted **only if "bioclim + MODIS NPP are fully present globally."**
  MODIS NPP is present for **31%** of land → **precondition fails → fallback
  not available.**
- Brief HALT behavior: *"if a dataset cannot be obtained, HALT and write
  BLOCKERS.md … Do NOT proceed to Phase 2 for any feature set that is
  incomplete."* The global feature set is incomplete → **halt.**
- *"A smaller honest atlas beats a complete fabricated one."* The sanctioned
  global fallback being unavailable, the **honest partial extension was
  surfaced to the user and approved**: predict only where the full real stack
  exists, flag those cells `transfer`, document the MODIS-absent remainder.

---

## Phase 2 — global grid + transfer-cell prediction

Script: `scripts/build_atlas_global.py` (new; reuses `build_atlas_lookup.py`
helpers verbatim so transfer cells are computed the same way as Asia cells).

- Global 0.5° grid, **Asia bbox [25,180]×[−10,80] excluded** so the 20,678
  Asia cells are never recomputed (all of them sit inside that rectangle —
  verified). 203,400 candidate non-Asia cells.
- IGBP land mask → 7,501 non-Asia land cells (MODIS footprint only).
- Sampled: WorldClim bioclim (global), MODIS npp/lst (footprint), **real
  SoilGrids rasters** (`data/raw/soilgrids/*_5-15cm_global_0p1.tif`, rescaled
  per `src.features.SOILGRIDS_SCALE`) — **not** the Asia-training NN imputation.
- Any-NaN drop on the 12 F+NPP features → **6,716** cells with the full
  bioclim+MODIS stack. Of those, **6,715 (100%)** also had complete real
  SoilGrids, so every transfer cell carries both `fnpp` and `fullmodis`
  blocks (same schema as Asia). 1 cell dropped for missing soil — not imputed.
- Predicted F+NPP, Full+MODIS, and the climate baseline (same baseline trainer
  + training parquet as the Asia build); anomaly = exp(pred − climate). Per-cell
  SHAP top-3 for both models. Köppen, IGBP biome, nearest-site distances.
- Every new cell tagged **`"domain": "transfer"`**.

**Gate 2 — anomaly sanity by continent (F+NPP, no degenerate collapse):**

| Region | transfer cells | median anomaly |
|---|---:|---:|
| North America | 4,038 | 1.035 |
| Oceania (Australia) | 2,223 | 1.101 |
| Africa (E/S, east of 25°E) | 454 | 1.044 |
| **South America** | **0** | — (no MODIS) |
| **Europe** (west of 25°E) | **0** | — (no MODIS) |

Spot checks: Iowa = Croplands/Dfa, nearest training site 6,943 km (true
cross-continent extrapolation); Australian outback = Open shrublands/BSh;
California Central Valley = Croplands/BSk. All plausible.

## Phase 3 — merged atlas_lookup.json

- Existing Asia cells loaded verbatim, tagged `domain: "training"`, then the
  6,715 transfer cells appended. **27,393 cells total, 38 MB.**
- **Gate 3 — Asia cells preserved:** diffed every Asia cell against the
  pre-build backup → **0 value mismatches** (only the `domain` key added);
  training cells keep their original order and positions; `models` block
  unchanged. Schema bumped `v3 → v4` (adds per-cell `domain` + a top-level
  `coverage` block describing the training/transfer split and the MODIS limit).
- File size 38 MB (well under the ~120 MB / GitHub 100 MB limits) — no
  payload reduction or grid coarsening needed.

## Status against the brief's gates
- Data acquired vs missing: **WorldClim ✅, SoilGrids ✅, MODIS ❌ (31% land)**.
- Cell counts: **20,678 training + 6,715 transfer = 27,393.** File size **38 MB**.
- Fallback taken: **honest partial extension** (predict where real MODIS exists;
  the global F+NPP-only fallback was unavailable, precondition unmet). Both
  models retained for transfer cells since real SoilGrids was obtained.
- **Transfer framing in the data: present** — every non-Asia cell flagged
  `domain: "transfer"`; Asia cells `domain: "training"`. UI badge/caveat is
  Phase 4 (MSHI-WEB).
- No model was trained/retrained. No figures, SHAP plots, or other non-atlas
  MSHI artifacts were generated.
- MODIS-absent regions (South America, most of Africa/Europe) are **omitted,
  not fabricated** — see `BLOCKERS.md`.
