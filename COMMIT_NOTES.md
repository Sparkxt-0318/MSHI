# Atlas global coverage — commit notes

**Branch:** `claude/atlas-global-lookup` (from `main`)
**Task:** Extend the interactive atlas to global land coverage, with all
non-Asia cells flagged as cross-continental transfer predictions.
**Date:** 2026-06-02
**Outcome:** **HALTED at the Phase 1 gate** — a required global feature layer
(MODIS NPP/LST/IGBP) is absent for 69% of land and cannot be obtained. See
`BLOCKERS.md`. No feature data fabricated; Asia cells untouched; no figures or
non-atlas artifacts produced.

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
- *"A smaller honest atlas beats a complete fabricated one."* No fabrication
  was performed. An honest **partial** extension (transfer cells over the 31%
  of land that has real MODIS) is possible and is offered as an option in
  `BLOCKERS.md` / the PR, pending a decision — it is not shipped unilaterally
  because it changes the scope from "global" and would render a visibly patchy
  map (South America blank) that needs explicit UI framing buy-in.

## Status against the brief's gates
- Data acquired vs missing: **WorldClim ✅, SoilGrids ✅, MODIS ❌** (recorded above).
- Cell counts / file size: **n/a — no global lookup written** (halted; Asia
  atlas unchanged at 20,678 cells / 28 MB).
- Fallback taken: **none** (precondition for the F+NPP-only fallback not met).
- Transfer framing: **not yet applied** (data + UI work is downstream of the
  halted build). The per-cell `domain` flag and UI transfer badge remain to be
  implemented once a complete global feature set exists.
- MSHI-WEB: **untouched** (Phase 4 depends on the global lookup).
- No figures, SHAP plots, or other non-atlas MSHI artifacts were generated.
