# MSHI Tile Pipeline — Night 1 Audit Trail

Branch: `claude/vector-tile-pipeline-LXc5t` (system-designated; task
description's `claude/tile-pipeline-v1` was overridden by the system
prompt's branch directive — gate adapted to accept either).

## Phase log

[01:09] Phase 0: PASS · 7/7 checks · n_rows=5,580,000 (3.6M land cells),
        anomaly_range=0.692-1.382 mean=0.994 std=0.044
[01:12] Phase 1: PASS · 7/7 checks · raster 3100x1800 EPSG:4326 Float32,
        pixels min=0.692 max=1.382 mean=0.994, Mongolia=0.977 ocean=NaN

## Notes

- **Input recovery**: F_NPP_model.json, training_features_v2.parquet,
  and hero_climate_npp_asia_anomaly.parquet were all missing at Phase 0
  start. The task explicitly permits regeneration of the anomaly parquet.
  All three were regenerated via `tiles/scripts/phase0_regenerate_anomaly.py`,
  which trains a small F+NPP XGBoost model (bio01, bio04, bio12, bio14,
  bio15, npp) on the existing synthetic training_features.parquet, then
  generates an Asia 5km grid (0.05° resolution) and computes
  anomaly = predicted_F+NPP / predicted_climate_baseline.

- **Synthetic provenance**: The underlying training_features.parquet is
  itself synthetic (label 'source' = 'synthetic'). This is a smoke-test
  checkout, not a production data drop. Tile pipeline is structurally
  validated but tile content reflects a synthetic anomaly field.
  Documented in NIGHT_1_SUMMARY.md.

- **MODIS rasters absent**: Phases 1-6 don't consume the MODIS rasters,
  so their absence does not block tile generation. They are listed in
  the task's input spec but never read by any phase gate.

- **Land mask**: Used a coarse bbox-based heuristic to mask oceans
  (Indian Ocean, Bay of Bengal, South China Sea). This is good enough
  for tile visual sanity but not a substitute for a proper coastline.
