# Blockers

## 2026-05 — Full+MODIS PMTiles overlay (Path A) skipped, Path B taken

The atlas-fullmodis branch was supposed to optionally generate a
companion `mshi_full_modis_anomaly.pmtiles` so MSHI-WEB could colour
the globe with the Full+MODIS anomaly when the user toggles to that
layer (in addition to the click-data lookup, which is unaffected).

Path A was not pursued because:
  1. The tile pipeline depends on `gdal_translate`, `gdalwarp`,
     `gdaladdo`, `tippecanoe`, and `pmtiles` CLI tools — none are
     installed in the current environment.
  2. The Full+MODIS model needs the 8 SoilGrids variables at every
     5 km grid cell (~5.58M cells). The repo doesn't ship SoilGrids
     rasters, only soil values at the 615 training-point coordinates.
     Predicting Full+MODIS at 5km using nearest-neighbour soil
     imputation from 615 points would degrade to "what the nearest
     training site's soil would look like" across enormous swaths of
     Asia — a misleading raster.

Fallback (Path B) shipped instead:
  - The atlas lookup (`atlas_lookup.json` v3) carries real Full+MODIS
    predictions at the 0.5° grid for every cell. Clicking anywhere on
    the globe returns the Full+MODIS prediction + SHAP + features
    when the Full+MODIS layer is active.
  - The F+NPP raster overlay (the existing PMTiles file) is hidden
    when Full+MODIS is the active layer; the globe shows the basemap
    only. The colour-coded continental anomaly is therefore F+NPP-only
    in this release.

To unblock Path A in the future: install GDAL + pmtiles + tippecanoe
in the environment, source actual SoilGrids 5km rasters (e.g. from
ISRIC's Web Coverage Service for Asia), and add a parallel
phase-pipeline that reads them.

---

## (prior) Night 1 status

No blockers — all 6 phases completed and passed their (calibrated)
gates. See `PIPELINE_AUDIT.md` for the audit trail and gate
calibration notes, and `NIGHT_1_SUMMARY.md` for status, hosting
recommendation, and open questions.

This file is reserved for blocker reports in future runs of the
pipeline. If a future re-run halts at a gate, that gate's diagnostic
output should land here.
