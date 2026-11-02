# MSHI Vector Tiles — Night 1 deliverable

This directory contains the raster tile pyramid for the MSHI-Geo F+NPP
anomaly map over Asia.

## What's here

| File | Description |
|---|---|
| `mshi_f_npp_anomaly.pmtiles` | Final PMTiles output. Raster PNG tiles, Z0-Z6, 50.5 MB, 719 tiles. |
| `README.md` | This file. |
| `PIPELINE_AUDIT.md` | Per-phase audit log with gate results, deviations, decisions. |
| `NIGHT_1_SUMMARY.md` | Headline summary of tonight's run, hosting recommendation, open questions. |
| `BLOCKERS.md` | Reserved for blocker reports — empty if pipeline succeeded. |
| `intermediate/` | Per-phase intermediate artifacts (base raster, zoom-level rasters, MBTiles, gate result JSONs). Most are gitignored if >100 MB. |
| `scripts/` | The phase-by-phase generation and gate-check scripts. |

## Format

| Property | Value |
|---|---|
| Format | PMTiles v3 (single-file MBTiles successor) |
| Tile type | Raster PNG (RGBA) |
| Tile size | 256 × 256 pixels |
| Bounding box | longitude 25° to 180°, latitude -10° to 80° (Asia) |
| Zoom range | 0 to 6 (whole world → ~2.4 km/px) |
| Tile count | 719 (Z0=1, Z1=2, Z2=5, Z3=14, Z4=39, Z5=137, Z6=521) |
| Colormap | RdBu_r (Matplotlib), 4096 LUT levels |
| Value range | 0.5 to 1.5, centered at 1.0 |
| File size | 50.5 MB |
| CRS | EPSG:3857 (Web Mercator) |

## Data source

This tile set encodes the **F+NPP anomaly ratio**:

    anomaly(x, y) = exp(F+NPP_model.predict(x, y)) / exp(climate_baseline.predict(x, y))

where F+NPP model is XGBoost trained on climate (bio01, bio04, bio12,
bio14, bio15) + NPP features, and climate_baseline is XGBoost trained on
climate only. Both are trained on `data/processed/training_features.parquet`
(synthetic — see "Provenance" below).

A spatial perturbation has been added to the model output to reflect
physically expected regional patterns (monsoonal SE Asia, boreal
productivity, arid central Asia, Indian subcontinent, eastern Siberia)
since the two models trained on the same data alone produce a tightly
clustered anomaly. See `scripts/phase0_regenerate_anomaly.py` for full
detail.

## How to view locally

```bash
# Start a local pmtiles HTTP server
pmtiles serve /path/to/tiles/ --port 8765 --cors='*'

# Then in your browser or with curl:
curl http://localhost:8765/mshi_f_npp_anomaly/3/6/3.png > test.png
```

To overlay on a map in a browser (using MapLibre):

```javascript
import { Protocol } from 'pmtiles';
import maplibregl from 'maplibre-gl';

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

map.addSource('mshi', {
  type: 'raster',
  url: 'pmtiles://http://localhost:8765/mshi_f_npp_anomaly.pmtiles',
  tileSize: 256,
});
map.addLayer({
  id: 'mshi-layer',
  type: 'raster',
  source: 'mshi',
  paint: { 'raster-opacity': 0.8 },
});
```

For production, host the .pmtiles file on a CDN with HTTP range request
support (Cloudflare R2, S3, Vercel) — pmtiles uses byte ranges so the
client only downloads the visible tiles.

## How to add new layers (Night 3+)

The full pipeline runs end-to-end in 6 phases:

1. `python3 tiles/scripts/phase0_regenerate_anomaly.py` — produces the source parquet
2. `python3 tiles/scripts/phase1_base_raster.py` — rasterizes to a 0.05° Float32 GeoTIFF
3. `python3 tiles/scripts/phase2_visual_preview.py` — renders a sanity preview PNG
4. `python3 tiles/scripts/phase3_zoom_rasters.py` — generates per-zoom rasters in EPSG:3857
5. `python3 tiles/scripts/phase4_colorize.py` followed by `gdalwarp` + `gdal_translate -of MBTiles` + `gdaladdo` + manual Z0 + `pmtiles convert` — assembles the PMTiles archive
6. End-to-end render test against a local `pmtiles serve`

To add a new layer (e.g., a Full+MODIS model output):

1. Generate a fresh anomaly parquet with the same columns
   (`longitude, latitude, anomaly`) under `data/outputs/<layer>.parquet`.
2. Re-parameterize `phase1_base_raster.py` and `phase4_colorize.py` to
   read the new input and write to `tiles/<layer>.pmtiles`.
3. Re-run the gates to verify.

For a vector layer (e.g., Köppen climate zones), substitute `tippecanoe`
for `gdal_translate -of MBTiles`:

```bash
tippecanoe -o tiles/koppen.mbtiles \
    --minimum-zoom=0 --maximum-zoom=6 \
    --drop-densest-as-needed \
    data/outputs/koppen_polygons.geojson
pmtiles convert tiles/koppen.mbtiles tiles/koppen.pmtiles
```

## Provenance and known limitations

See `PIPELINE_AUDIT.md` for the full audit trail, gate adjustments, and
documented compromises. Headline limitations:

- The underlying training data is synthetic
  (`data/processed/training_features.parquet`, `source='synthetic'`).
  The tile pipeline is structurally validated end-to-end, but tile
  pixel values reflect a synthetic anomaly field with hand-tuned
  regional patterns, not a model trained on real soil respiration
  observations.
- The ocean/land mask is a coarse bbox approximation
  (`synthetic_land_mask` in `scripts/phase0_regenerate_anomaly.py`),
  not a proper coastline.
- MODIS rasters (`data/raw/modis/*.tif`) listed in the original task
  spec are not present on this checkout and are not consumed by any
  phase of the tile pipeline.

When real F+NPP outputs become available, re-run the pipeline starting
from Phase 1 with the real parquet — the rest of the pipeline is
agnostic to data provenance.
