# Claude Code prompt — MSHI-Geo hero map run

Paste the block below into Claude Code (or use it as your opening message
in a Claude Code session). Make sure you're in the unzipped `mshi-geo/`
directory before starting.

---

```
You are helping me execute the MSHI-Geo pipeline to produce a hero map
of climate-corrected soil microbial respiration anomaly across Asia,
validated on a US held-out subset. This is for the Genius Olympiad
science category. The pipeline code is already written and tested with
synthetic data — your job is to run it against real datasets, fix issues
as they come up, and produce the final hero map.

## What I need from you, in order

### Phase 1: Verify environment

1. Run `bash run.sh demo` to confirm the pipeline works end-to-end
   on synthetic data. This should complete in <1 minute and produce
   files in data/outputs/. If it fails, fix it before moving on.

2. Verify Python deps: `pip install -r requirements.txt`. Add anything
   missing for geopandas (it sometimes needs system libs like GDAL).

### Phase 2: Pull data

Run `bash run.sh download` and walk me through what it produces.
SoilGrids should download automatically via WCS for the Asia bounding
box (this can take 30-60 minutes — let it run). For everything else,
the script prints manual-download instructions.

You will need my help for:
- COSORE: I'll run the R commands or download CSVs from GitHub
- SRDB: I'll download srdb-data.csv and srdb-studies.csv from GitHub
- WorldClim: I'll download the bioclim zip
- MODIS NPP / LST / landcover: I'll run the Google Earth Engine
  scripts you give me, then save the exported GeoTIFFs to my Drive
  and copy them to data/raw/modis/
- Natural Earth borders: hero_map.py tries to fetch automatically;
  if it fails, I'll download manually

For each manual step, give me the exact URLs and commands. After I
confirm a download is done, verify the file exists at the expected path
before proceeding.

### Phase 3: Build training table

Run `python src/build_target.py`. This loads SRDB + COSORE and produces
data/processed/respiration_points.parquet.

CRITICAL: COSORE files might have different column names than the script
expects. If the loader fails or returns 0 rows, inspect the CSV with
`pd.read_csv(...).head()` and `pd.read_csv(...).columns`, then update
the column name mapping in load_cosore() inside src/build_target.py.

Print a summary: total points, Asia count, US count, mean Rs, range.
If the Asia count is below 1500, flag this as a data-coverage risk —
we may need to broaden filtering or relax the manipulation filter.

### Phase 4: Extract features and train

Important: a proper extract_features_real.py module that joins the
training points with the SoilGrids/WorldClim/MODIS rasters does not
yet exist. You need to write it. Use src/features.py as the building
block — it already has extract_at_points() and default_registry().
The new script should:

1. Load data/processed/respiration_points.parquet
2. Build the raster registry from configs/mshi_geo.yaml feature lists
3. Sample all rasters at the training points
4. Add engineered features (c_n_ratio, aridity_demartonne, etc.)
5. Save to data/processed/training_features.parquet
6. Also build the 5km Asia prediction grid by sampling rasters across
   the full bbox; save to data/processed/asia_grid_5km.parquet
7. Same for the US validation subset; save to
   data/processed/us_validation_features.parquet

After it works, run `bash run.sh train`. Show me the spatial CV results
and the SHAP top features. We want to see SOC, NPP, and temperature
near the top — that confirms the model is learning real biology.

### Phase 5: Validate, predict, composite, hero

Run in sequence:
- `bash run.sh validate`   (Asia → US transfer test)
- `bash run.sh predict5km` (grid prediction + anomaly composite)
- `bash run.sh hero`       (render hero map)

After each step, show me the key numbers:
- CV mean R²
- Asia → US transfer R²
- Anomaly composite stats (% degraded, % healthy)

Then show me data/outputs/hero_mshi_geo_asia_screen.png.

### Phase 6: Diagnose and iterate

If transfer R² < 0.30: this is a real problem.
Diagnose options in this order:
1. Check for data leakage (any sites at <50km between train and test?)
2. Check feature distributions: are Asian and US features in the same
   range, or is the model extrapolating outside training distribution?
3. Try adding more features (additional bioclim, soil depths)
4. Consider regional sub-models (e.g., temperate-only training)

If anomaly map looks like noise rather than coherent patterns: check
that the climate baseline is using fewer features than the full model
(it should be 5 climate features only). If they're identical the
anomaly will collapse to ~1.0 everywhere.

If degradation hotspots don't roughly match known degradation zones
(North China Plain, Indo-Gangetic Plain, Central Asian steppes), the
model probably isn't capturing soil-specific signal. Show me the
component SHAP — if SOC isn't in the top 3 drivers, something is wrong.

### Phase 7: 1km hero (only after 5km looks good)

Once the 5km hero looks coherent and validation numbers are defensible:

```
bash run.sh predict1km
bash run.sh hero1km
```

This is slow (1-3 hours). Run it overnight if needed.

## Constraints / preferences

- Don't modify the visual style of hero_map.py — Bedrock aesthetic is
  locked. If layout breaks because of long labels or different bbox,
  fix the bbox or labels, not the styling.
- Always show me the actual numbers (R², counts, ranges) before
  proclaiming success. I want honest reporting, not optimism.
- If a download or run takes more than 10 minutes, kick it off in the
  background and come back to it.
- If something fundamental breaks (e.g., COSORE schema completely
  different), stop and ask me before improvising.
- Treat the Asia → US transfer R² as the primary scientific success
  metric. CV R² being high is necessary but not sufficient.

## When you're done

Show me:
1. data/outputs/hero_mshi_geo_asia_screen.png
2. data/outputs/training_metrics.json
3. data/outputs/validation_report.json
4. A short summary: did the model work, what are the headline numbers,
   and what should I be cautious about in the pitch.

Now start with Phase 1.
```
