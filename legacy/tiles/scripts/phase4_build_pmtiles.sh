#!/usr/bin/env bash
# Phase 4 driver: build MBTiles + PMTiles from base raster.
# Idempotent: deletes prior intermediates before rebuilding.
set -euo pipefail

cd "$(dirname "$0")/../.."

INTER=tiles/intermediate
OUT=tiles/mshi_f_npp_anomaly.pmtiles

rm -f "$INTER/asia_anomaly_rgba.tif" \
      "$INTER/asia_anomaly_rgba_3857.tif" \
      "$INTER/asia_anomaly_rgba_3857_z6.tif" \
      "$INTER/mshi.mbtiles" \
      "$OUT"

# Step 1: colorize Float32 base → RGBA GeoTIFF
python3 tiles/scripts/phase4_colorize.py

# Step 2: reproject to web mercator at Z6 resolution
gdalwarp -t_srs EPSG:3857 -tr 2445.98 2445.98 -r bilinear \
    "$INTER/asia_anomaly_rgba.tif" \
    "$INTER/asia_anomaly_rgba_3857_z6.tif" 2>&1 | tail -2

# Step 3: gdal_translate to MBTiles (base Z6)
gdal_translate -of MBTiles \
    -co TILE_FORMAT=PNG \
    -co RESAMPLING=BILINEAR \
    "$INTER/asia_anomaly_rgba_3857_z6.tif" \
    "$INTER/mshi.mbtiles" 2>&1 | tail -2

# Step 4: build overview pyramid Z5..Z1
gdaladdo -r average "$INTER/mshi.mbtiles" 2 4 8 16 32 64 2>&1 | tail -2

# Step 5: render Z0 directly from base raster (NOT downsampled from Z1)
python3 tiles/scripts/phase4_z0_from_base.py

# Step 6: convert MBTiles → PMTiles
pmtiles convert "$INTER/mshi.mbtiles" "$OUT" 2>&1 | tail -3

ls -lh "$OUT"
pmtiles show "$OUT" 2>&1 | grep -E "min zoom|max zoom|bounds|addressed tiles"
