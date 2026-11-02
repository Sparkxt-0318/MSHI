# Run B blockers

*2026-05-03, branch `claude/run-b-modis`*

## BLOCKER 1 — MODIS acquisition (hard blocker, unrecoverable in this environment)

**What was attempted:**
1. `earthengine-api` Python package — `ee.Initialize()` returns `EEException:
   Please authorize access to your Earth Engine account by running
   earthengine authenticate ...`. Interactive browser auth is unavailable in
   this sandbox; no service-account JSON or cached credentials exist under
   `/root/.config/earthengine/` or anywhere in the home directory.
2. Direct LP DAAC URLs (e.g. `https://e4ftl01.cr.usgs.gov/...`) — require
   NASA Earthdata login (browser-based OAuth). Not available here.
3. AWS-mirrored MODIS bucket (`https://nasa-modis.s3.amazonaws.com/`) —
   returns HTTP 403 anonymous.
4. NASA NEO, NASA AppEEARS — likewise require Earthdata credentials.
5. LP DAAC product page returns HTTP 503 to anonymous probes.

**Conclusion:** MODIS NPP (MOD17A3HGF), LST_Day/Night (MOD11A2), and
IGBP land-cover (MCD12Q1) cannot be acquired in this environment without
out-of-band credentialing. The user's preamble noted this would likely
fail in non-interactive mode and instructed me to "document the failure
and fall back ... else proceed with the remaining checkpoints."

**Knock-on consequences for Run B as specified:**
- **Checkpoint 3** (re-extract features with MODIS): cannot run; the
  `data/raw/modis/` directory is empty.
- **Checkpoint 4** (F+NPP, Full+MODIS configs): **F+NPP is impossible
  without NPP**. **Full+MODIS is impossible.** I cannot produce
  `sweep_results_v2.json` with the new MODIS configurations.
- **Checkpoint 5** (IGBP biome stratification): IGBP land-cover is the
  required class label. **Substitute used:** Köppen-Geiger climate-zone
  stratification, computable directly from WorldClim bioclim variables.
  This is a different stratification (climate zones rather than land-
  cover classes) but addresses the same scientific question of within-
  vs cross-region transfer. Documented as such in the analysis output.
- **Checkpoint 6** (heroes + methodology evolution panel): the
  evolution panel as specified requires F+NPP and Full+MODIS hero maps.
  **Substitute approach:** the panel will use F (climate-only) and B
  (full features) hero maps that already exist from Run A, plus the new
  Köppen-stratified heroes, with a clear caption that MODIS-dependent
  panels are pending the user's GEE export.
- **Checkpoint 7** (paper updates): MODIS-related paragraphs will be
  marked `[PENDING MODIS]` rather than fabricated. The biome-
  stratification section will reference Köppen zones with an explicit
  note that IGBP-stratified results are pending.

**What the user needs to do to unblock the rest of Run B:**

Either:
- Run the GEE script in the user's preamble and push the four exported
  TIFFs to `data/raw/modis/` (filenames `npp_2020_2024_mean.tif`,
  `lst_day_2020_2024_mean.tif`, `lst_night_2020_2024_mean.tif`,
  `landcover_igbp_2023.tif`).
- Or place a Google service-account JSON in
  `/root/.config/earthengine/credentials` and tell me to retry. The
  service account needs Earth Engine access enabled and read on the
  MODIS collections.
- Or place a `.netrc` with NASA Earthdata credentials in `/root/`
  (machine `urs.earthdata.nasa.gov`, login & password) and tell me to
  retry. I'd then download MOD17A3HGF, MOD11A2, MCD12Q1 directly from
  LP DAAC.

Once any of these is in place, re-running `bash run.sh` from
Checkpoint 3 onward will complete the full Run B.

## What I'm doing instead (best-judgment fallback path)

1. Köppen-Geiger climate-zone stratification using only WorldClim
   bioclim variables. Five top-level Köppen classes (A=tropical,
   B=arid, C=temperate, D=continental, E=polar) computable from bio01,
   bio12, bio14, bio17 plus monthly extrema. Stratify Asia training
   sites and US validation sites by class; train F (climate-only) per
   class; report within-class transfer R².
2. Re-confirm the Run A v1 numbers on this branch (sweep_results.json
   is from main; bootstrap_ci.json from Run A). No retraining required.
3. Update paper draft minimally: note MODIS is pending, add Köppen
   section. Mark MODIS sections `[PENDING MODIS]`.
4. Build a partial methodology evolution panel: F (climate-only),
   B (full features), Köppen-best, Köppen-worst. Include a fifth
   placeholder pane noting "MODIS-NPP model — pending exports."

This gets the structural and analytical scaffolding ready so that when
MODIS lands the user only has to drop in the rasters and re-run from
Checkpoint 3.
