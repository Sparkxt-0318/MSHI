# BLOCKERS — Atlas global coverage (`claude/atlas-global-lookup`)

**Status: HALTED at the Phase 1 data-acquisition gate.**
**Date:** 2026-06-02

The global atlas build cannot proceed because a required feature layer —
**MODIS NPP + LST (and IGBP land cover)** — is **not available for most of
the globe** and **cannot be obtained** in this environment. No feature data
was fabricated, synthesized, or substituted to fill the gap.

This is the layer the task brief assumed was already global:

> "MODIS NPP, LST day/night, IGBP land cover — per PR #11 these EXIST and
> cover the globe (lon -125..180, lat -39..88). **Verify and note actual
> global coverage.**"

Verified. The bounding box is wide, but the **actual data footprint is not
global.** It covers only the original Asia + US (+ Australia) study regions.

---

## The failed layer: MODIS NPP / LST / IGBP

### What is on disk (`data/raw/modis/`)
| File | Bounds (lon / lat) | Notes |
|---|---|---|
| `npp_2020_2024_mean.tif` | lon[-125, 180] lat[-39, 88] | data only in Asia/Oceania/US box; NaN elsewhere |
| `lst_day_2020_2024_mean.tif` | lon[-125, 180] lat[-39, 88] | same footprint |
| `lst_night_2020_2024_mean.tif` | lon[-125, 180] lat[-39, 88] | same footprint |
| `landcover_igbp_2023.tif` | lon[-180, 180] lat[-39, 88] | 0 (water) outside the study footprint |

The *bounding box* spans the globe, but the *valid data* is the union of two
GEE export regions: an **eastern box (~25–180°E, −39–88°N)** and a **US box
(−125 to −66°W, 24–50°N)**. Everything between them — the Atlantic, South
America, western/central Africa, Europe, western Russia — is NaN / fill.

### Actual MODIS coverage of global land (sampled on the 0.5° atlas grid)
Land reference = WorldClim `bio01` valid (global). MODIS-valid = `npp > 0`
**and** `lst_day` finite.

```
Global land cells (0.5°):           89,773
Land cells WITH MODIS npp+lst:      27,813   (31.0% of land)
Land cells WITHOUT MODIS:           61,960   (69.0% of land)  ← F+NPP cannot run
```

| Continent | land cells | with MODIS | coverage |
|---|---:|---:|---:|
| South America | 6,391 | 0 | **0.0 %** |
| Africa | 11,906 | 2,390 | 20.1 % |
| Europe | 4,471 | 1,400 | 31.3 % |
| North America | 11,845 | 4,108 | 34.7 % |
| Asia (training) | 23,011 | 17,356 | 75.4 % |
| Oceania | 3,120 | 2,244 | 71.9 % |

**69% of global land — all of South America, ~80% of Africa, ~70% of
Europe — has no MODIS NPP/LST.** Both headline models depend on MODIS:

- **F+NPP** (12 features) needs `npp, lst_day, lst_night, lst_diurnal_range`.
- **Full+MODIS** (34 features) needs those plus the 10 IGBP land-cover one-hots.

Without MODIS a cell drops out (any-NaN rule in `build_atlas_lookup.py`), so
neither model can produce a prediction over 69% of land.

### Why global MODIS could not be obtained
The model was trained on three specific MODIS products, in specific units, as
a **2020–2024 mean**: MOD17A3HGF (annual NPP), MOD11A2 (8-day LST), MCD12Q1
(yearly IGBP land cover). To stay faithful to the trained model, any global
replacement must be **the same products in the same units** — not a different
NPP/LST dataset (that would be a forbidden substitution).

| Route attempted | Result |
|---|---|
| Google Earth Engine (`earthengine-api`) — the path documented in `src/download.py` | `import ee` → `ModuleNotFoundError`; GEE also requires an authenticated account / service credentials, which are not present. |
| NASA LP DAAC direct (MOD17A3HGF / MOD11A2 / MCD12Q1) | Requires Earthdata Login credentials (not present). |
| Microsoft Planetary Computer STAC (anonymous) — `https://planetarycomputer.microsoft.com/api/stac/v1` | Reachable. Hosts `modis-17A3HGF-061` (NPP) and `modis-11A2-061` (LST), **but NOT `modis-12Q1`** (IGBP land cover) → no global land-cover one-hots / biome layer. |
| Build the 2020–2024 LST mean client-side from MS-PC COGs | Infeasible in one run: MOD11A2 is 8-day → 46/yr × 5 yr × ~286 global sinusoidal tiles ≈ **65,000 COG reads** to average, each needing per-asset signing + sinusoidal→EPSG:4326 reprojection. Not tractable overnight, and 0.05° CMG products (MOD11C3) that would make it tractable are LP-DAAC/Earthdata-gated. |

**Conclusion:** MODIS NPP/LST/IGBP cannot be obtained globally here without
Earthdata or Google Earth Engine credentials. No substitute was used.

---

## What WAS successfully acquired (the layers the brief flagged as missing)

Both layers the brief expected to be the hard part downloaded cleanly and
were validated — they are **not** the blocker.

| Layer | Source | Result |
|---|---|---|
| **WorldClim 2.1 bioclim** (bio01/04/05/06/12/14/15/17), 10-arcmin | `geodata.ucdavis.edu/.../wc2.1_10m_bio.zip` (49.9 MB) | ✅ Global. Verified data on every continent (Amazon, Sahara, Europe, Patagonia). In `data/raw/worldclim/`. |
| **SoilGrids 2.0** (soc/nitrogen/phh2o/clay/sand/silt/bdod/cec), 5–15cm mean | ISRIC WCS `maps.isric.org/mapserv` | ✅ Global @0.1° (~13 MB). Units rescaled per `src/features.py SOILGRIDS_SCALE` and **validated against training**: medians match (phh2o 6.2 vs 5.9; bdod 1.23 vs 1.20; nitrogen 2.3 vs 2.14; soc 28.1 vs 27.5). In `data/raw/soilgrids/`. Real rasters — **not** the Asia-training NN imputation (which the brief correctly forbids globally). |

See `data/raw/ACQUISITION_MANIFEST.json` for per-file extents and sizes.

---

## Paths forward (need a decision — see PR)

The global build is blocked, but two of three missing layers are now in hand.
Options, in order of fidelity:

1. **Provide MODIS access** (Earthdata Login or a GEE service account). With
   credentials I can fetch global MOD17A3HGF / MOD11A2 / MCD12Q1 (2020–2024
   mean), and the full global build proceeds exactly as specified.
2. **Honest partial extension** — build transfer cells only where real MODIS
   already exists (the 31% of land: North America, Australia, parts of
   Africa/Europe), flag them `domain: "transfer"`, and leave South America /
   most of Africa & Europe out, documented as MODIS-absent. This is "a smaller
   honest atlas." Caveat: the rendered map would be visibly patchy (South
   America entirely blank), so it needs explicit framing in the UI.
3. **Hold** — keep the Asia-only atlas as-is until global MODIS is available.

Per the brief's rules, the sanctioned reduced fallback (F+NPP-only global) is
**not** available: it is permitted *only if* "bioclim + MODIS NPP are fully
present globally," and MODIS NPP is present for just 31% of land.

**Nothing downstream was fabricated.** No global `atlas_lookup.json` was
written; Asia cells are untouched; no MSHI-WEB changes were made.
