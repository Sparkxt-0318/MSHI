# BLOCKERS — Atlas US coverage (Phase 0 HARD GATE: HALTED)

**Task:** Extend the interactive atlas to the continental US, with US cells
framed as cross-continental transfer predictions of the existing
Asia-trained F+NPP and Full+MODIS models. Phase 1 (this repo, MSHI) was to
generate US grid cells at 0.5° and append them to `atlas_lookup.json`.

**Verdict: HALTED at the Phase 0 hard gate. No US cells were generated.**

The US-extent feature data required to compute *real* F+NPP / Full+MODIS
predictions on a 0.5° US grid **does not exist on disk**. Per the task's
explicit Phase 0 HALT rule — *"If US-extent feature rasters/data do NOT
exist on disk, HALT immediately… Do NOT fabricate, synthesize, or
substitute Asia data for US cells… The US extension is impossible without
real US feature data — say so plainly and stop."* — I stopped, documented
the exact gaps below, and did nothing else.

Nothing was fabricated, synthesized, or substituted. No model was trained
or retrained. `atlas_lookup.json` was **not** modified (still 20,678 Asia
cells, 29.12 MB). No UI / MSHI-WEB work was started.

---

## How the atlas is built (so the gap is unambiguous)

`scripts/build_atlas_lookup.py` builds each cell by **sampling real
rasters at the cell center**:

- 8 WorldClim bioclim rasters → `data/raw/worldclim/wc2.1_10m_bio_{1,4,5,6,12,14,15,17}.tif` (script lines 79–88, 342–346)
- 3 MODIS rasters (npp, lst_day, lst_night) → `data/raw/modis/*.tif` (lines 89–93, 349–356)
- IGBP land cover (land mask + biome) → `data/raw/modis/landcover_igbp_2023.tif`
- SoilGrids 8 vars → **not from a raster**; nearest-neighbour imputed from the 615 Asia training sites in `training_features_v2.parquet` (lines 402–422)

Both models depend on the 8 bioclim variables:

- **F+NPP** (12 features): `bio01, bio04, bio05, bio06, bio12, bio14, bio15, bio17, npp, lst_day, lst_night, lst_diurnal_range`
- **Full+MODIS** (34 features): the 8 SoilGrids vars + the 8 bioclim vars + 4 engineered + npp/lst_day/lst_night/lst_diurnal_range + 10 land-cover one-hots

A US cell cannot be predicted by either model unless all 8 bioclim values
exist for it. For Full+MODIS, the 8 SoilGrids values are also required.

---

## Phase 0 inventory — exactly what is / isn't on disk, and over what extent

| Layer (needed for US cells) | Used by | Present on disk? | Extent | Covers continental US (−125..−66 lon, 24..50 lat)? |
|---|---|---|---|---|
| `scripts/build_atlas_lookup.py` | pipeline | ✓ | n/a | n/a |
| `F_NPP_model.json` (12 feat) | F+NPP | ✓ | n/a | n/a |
| `Full_MODIS_model.json` (34 feat) | Full+MODIS | ✓ | n/a | n/a |
| MODIS NPP raster | both | ✓ | lon [−125.001, 179.999], lat [−39.181, 87.819], 0.05° | **YES** |
| MODIS LST day raster | Full+MODIS | ✓ | lon [−125.001, 179.999], lat [−39.181, 87.819], 0.05° | **YES** |
| MODIS LST night raster | Full+MODIS | ✓ | lon [−125.001, 179.999], lat [−39.181, 87.819], 0.05° | **YES** |
| IGBP land cover raster | both (mask/biome) | ✓ | lon [−180, 180], lat [−39.326, 87.874], 0.05° | **YES** |
| **8 WorldClim bioclim rasters** | **both** | **✗ MISSING** | `data/raw/worldclim/` does not exist; no `*bio_*`/`wc2*`/`bioclim` file anywhere on the filesystem | **NO — required, absent over every extent** |
| **8 SoilGrids rasters** | **Full+MODIS** | **✗ MISSING** | `data/raw/soilgrids/` does not exist; no SoilGrids raster anywhere | **NO — required for Full+MODIS, absent** |

`.gitignore` excludes `data/raw/`; only the 4 MODIS rasters were
force-committed. The WorldClim and SoilGrids rasters were never committed
(the build-script header notes WorldClim was "downloaded for this script"
as a ~310 MB transient and SoilGrids was never sampled from a raster at
all). They are therefore gone, for the US **and** for Asia — the existing
Asia atlas could not be rebuilt right now either without re-downloading
WorldClim.

### The decisive blockers

1. **8 WorldClim bioclim variables have no US-extent raster (or any
   raster) on disk.** They are mandatory inputs to *both* models. Without
   them, zero US cells can be predicted by either model.
2. **8 SoilGrids variables have no US-extent raster on disk.** Mandatory
   for Full+MODIS. The Asia atlas filled these by nearest-neighbour from
   the 615 **Asia** training sites; reusing that for US cells would be
   "substituting Asia data for US cells," which the task explicitly
   forbids.

The MODIS layers (NPP, LST, IGBP) *do* cover the US, but they are useless
in isolation: neither model can run on MODIS features alone.

---

## What US data DOES exist — and why it cannot substitute

The only US feature data on disk is point validation data, not a grid:

| File | Rows | What it is | Lon / Lat extent |
|---|---|---|---|
| `data/processed/us_validation_features_v2.parquet` | 274 | Scattered US validation **point sites** with measured Rs + full 32-col feature set (bioclim, soilgrids, MODIS, engineered) | lon [−124.90, −66.38], lat [27.36, 49.76] |
| `data/processed/us_validation_features.parquet` | 274 | Older 28-col version of the same sites | same |

These are the held-out US validation points behind the published transfer
R² (F+NPP n=223 usable, R²=+0.145). They are **274 clustered research
locations, not a 0.5° gridded surface.**

A continental-US 0.5° grid (−125..−66 lon × 24..50 lat) is 118 × 52 =
6,136 gross cells; the land subset is on the order of **3,000–4,000
cells**. Filling 3,000–4,000 grid cells of bioclim from 274 clustered
points — whether by interpolation or by the script's nearest-neighbour
trick — would be **synthesizing a feature surface that does not exist**.
That is exactly the fabrication the Phase 0 gate forbids, and the result
would not share "the SAME feature definitions used for the Asia cells"
(which were sampled from real WorldClim rasters at each cell center).

No `*_grid_*` US parquet exists; `data/processed/` contains only Asia
grids and these two US point files.

---

## Why I did not just download WorldClim / SoilGrids

- The Phase 0 gate is keyed on what is **on disk** and instructs HALT, not
  acquisition: *"No real US feature data → halt, document, do nothing
  else."*
- Even with a fresh WorldClim download, the SoilGrids gap remains: the
  Asia atlas never used a real SoilGrids raster (it NN-imputed from Asia
  training sites). To match the Asia cells' provenance for the US, the
  only on-hand SoilGrids source is Asia training sites — forbidden — or
  274 US points — synthesis. So Full+MODIS US cells could not be produced
  faithfully even after a WorldClim download.
- Re-acquiring large external datasets and rebuilding is precisely the
  "do nothing else" the gate rules out, and a re-download risks a version
  mismatch with the WorldClim build used for the Asia cells.

---

## What was explicitly NOT done (honesty log)

- ✗ No US cells generated; `atlas_lookup.json` unchanged (20,678 Asia
  cells, 29.12 MB, no `domain` field added).
- ✗ No fabricated / synthesized / interpolated US features.
- ✗ No Asia data substituted for US cells.
- ✗ No model trained or retrained.
- ✗ No Phase 2 / UI work; **MSHI-WEB was not touched** and its
  `claude/atlas-us-coverage` branch was not created.

---

## Exact unblock path

To make the US extension possible (no retraining required — feature
extraction only):

1. Add **US-extent WorldClim 2.1 bioclim rasters** for bio01, bio04,
   bio05, bio06, bio12, bio14, bio15, bio17 at `data/raw/worldclim/`
   (same 10′ product the Asia cells used), covering at least
   −125..−66 lon, 24..50 lat.
2. Add **US-extent SoilGrids rasters** for soc, nitrogen, phh2o, clay,
   sand, silt, bdod, cec over the same extent — so US SoilGrids comes from
   real US soil, not Asia training-site NN.
3. Extend `ASIA_BBOX` handling in `build_atlas_lookup.py` to also emit a
   US grid (or add a `--bbox` / `--region us` flag), tag those cells
   `"domain": "transfer"` (and tag Asia cells `"domain": "training"`),
   and append them. The MODIS NPP/LST/IGBP rasters already on disk cover
   the US and need no change.
4. Re-run the build; proceed to Phase 1 GATE checks and then Phase 2.

---

## Note on branch / docs

- This BLOCKERS.md is committed to **`claude/atlas-us-lookup`** — the branch
  the task names for Phase 1 — cut from the branch holding the build script
  and both trained models (`claude/compassionate-ride-EuWTt`, the session's
  designated MSHI branch). If you'd prefer the halt recorded on the session
  branch instead, say so and I'll move it.
- The existing `COMMIT_NOTES.md` in this repo documents a **different,
  prior task** ("Atlas figure regen 2026") and was intentionally left
  untouched. No new COMMIT_NOTES.md was written because there is no Phase 1
  build to report (no US cell count, no file-size change) — BLOCKERS.md is
  the appropriate artifact for a Phase 0 halt.
