# Item 1 — pre-flight blockers

*2026-05-05, branch `claude/item-1-modis` (off `claude/modis-rasters-v2`).*

## Pre-flight result: STOPPED before any model training

Per the explicit pre-flight rule in the Item 1 prompt
(*"If any check fails, log to `data/outputs/RUN_ITEM_1_BLOCKERS.md` and STOP."*),
no F+NPP, Full+MODIS, sweep_results_v2, hero, evolution-panel or
SHAP-v2 work was attempted. Two of the pre-flight inputs failed:

### Blocker 1 — three of four MODIS rasters are 2-byte placeholders

```
data/raw/modis/npp_2020_2024_mean.tif         2 bytes  ← \r\n only
data/raw/modis/lst_day_2020_2024_mean.tif     2 bytes  ← \r\n only
data/raw/modis/lst_night_2020_2024_mean.tif   2 bytes  ← \r\n only
data/raw/modis/landcover_igbp_2023.tif    455,188 bytes  ← REAL raster
```

The three placeholder TIFFs contain the literal two-byte sequence
`\r\n` (CRLF) and nothing else. `rasterio.open()` rejects them with
`CPLE_OpenFailedError: not recognized as being in a supported file format`.
F+NPP requires NPP, lst_day, lst_night, and the engineered
lst_diurnal_range. Full+MODIS additionally needs landcover one-hot
encoded. With three of the four MODIS rasters missing, neither
configuration can be trained without fabricating data, which the
prompt explicitly forbids ("*Use ONLY existing data*").

The fourth raster, `landcover_igbp_2023.tif`, IS a real
2,544 × 7,200 uint8 GeoTIFF in EPSG:4326 at 0.05° resolution
(±180° longitude, −39.3° to +87.9° latitude). IGBP class counts
(7.0 M valid pixels, 50.9% class 17 = water, the rest distributed
across classes 1–16) are plausible.

### Blocker 2 — `training_features.parquet` is the synthetic demo

The git-tracked parquet has 3,000 rows with `source = 'synthetic'`
and `site_id` values like `site_0, site_1, ...`. This is the output
of `src/demo_synthetic.py`, not the real Asian training table. The
pre-flight rule states the file should have 615 rows and a real
respiration target.

The good news: the **real** points exist as
`data/processed/respiration_points.parquet` (1,393 sites:
615 Asia + 274 US + 504 other; sources 1,343 SRDB + 50 COSORE),
and all the raw rasters needed to regenerate `training_features.parquet`
are intact on this branch:

```
data/raw/worldclim/  : wc2.1_30s_bio_{1,4,5,6,12,14,15,17}.tif (real)
data/raw/soilgrids/  : 16 tiles (8 vars × Asia/US, real)
data/raw/srdb/       : srdb-data.csv, srdb-studies.csv (real)
data/raw/cosore/     : cosore_annual.csv (real, 66 sites)
```

## What I did NOT do (per the STOP rule)

- Checkpoint 1 (sample MODIS at 615 training points)        ←  blocked, 3/4 rasters missing
- Checkpoint 2 (F+NPP)                                      ←  blocked
- Checkpoint 3 (Full+MODIS)                                 ←  blocked
- Checkpoint 4 (sweep_results_v2.json)                      ←  blocked (inputs from C2/C3 missing)
- Checkpoint 5 (F+NPP hero map)                             ←  blocked
- Checkpoint 6 (SHAP v2 + evolution panel)                  ←  blocked (depends on C2/C3 outputs)
- Checkpoint 7 (paper update + Item 1 summary)              ←  blocked of substantive content

The branch `claude/item-1-modis` was created from
`claude/modis-rasters-v2` per the prompt, and contains only this
blockers file plus the parent's existing tree. No model training,
no MODIS sampling, no figure generation, no paper edits.

## What the user needs to do to unblock Item 1

Push real GeoTIFFs to the four expected paths in `data/raw/modis/`:

```
npp_2020_2024_mean.tif         (MOD17A3HGF, mean 2020–2024,
                                Asia bbox 25–180°E, −10–80°N or wider)
lst_day_2020_2024_mean.tif     (MOD11A2 LST_Day_1km mean, Celsius;
                                the GEE script subtracts 273.15)
lst_night_2020_2024_mean.tif   (MOD11A2 LST_Night_1km mean, Celsius)
landcover_igbp_2023.tif        ← already real, no action needed
```

The Item 1 prompt's GEE export script in the user's prior preamble
already produces these. After pushing, re-trigger Item 1 from
pre-flight and Checkpoints 1–7 will run as specified.

## Optional fallback the user could authorise (NOT taken in this run)

Because the real `landcover_igbp_2023.tif` IS available, an
*IGBP-stratified F-only* analysis is possible without NPP / LST.
This is the analysis I substituted with Köppen-Geiger zones in
Run B (see `RUN_B_BLOCKERS.md` and `koppen_stratification.md`),
because back then no MODIS raster was available at all. The IGBP
stratification answers a slightly different question: does
land-cover stratification (forest-only, cropland-only, etc.)
recover transfer where Köppen climate-zone stratification did not?

Running it would also require regenerating
`training_features.parquet` from `respiration_points.parquet`
(15-minute job using the existing `src/extract_features_real.py`),
since the tracked file is synthetic.

I did NOT do either of these because the user's pre-flight rule is
explicit: "If any check fails, log to BLOCKERS.md and STOP." If the
user prefers the optional IGBP-stratified fallback, send a one-line
"do the IGBP fallback" and I'll execute it next session.

## Open question for the user

Three options — the user picks:

1. **Push the missing NPP / lst_day / lst_night TIFFs**, then
   re-run Item 1 from pre-flight. This produces the F+NPP and
   Full+MODIS results the prompt actually asks for.
2. **Authorise the IGBP-stratified fallback.** Substitute a
   landcover-only stratification analysis into Item 1. Documented as a
   substitute, not a replacement for F+NPP. Would also regenerate
   the corrupted `training_features.parquet` from respiration_points.
3. **Wait for the cross-continental MODIS run.** The user's preamble
   notes Item 1 is Asia-only and a follow-up run will do the
   full cross-continental MODIS test. The follow-up depends on the
   same NPP / LST rasters, so option 3 is practically equivalent to
   option 1 in terms of what needs to happen first.

The path that maximises pitch-deck impact in the shortest wall-clock
time is option 1.
