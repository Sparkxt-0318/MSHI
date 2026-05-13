#!/usr/bin/env bash
# tiles/run.sh — idempotent runner for the MSHI vector tile pipeline.
#
# Re-runs all 6 phases + their gates from scratch. Skips any step
# whose output already exists, unless --force is passed.
#
# Usage:
#   tiles/run.sh           # incremental: skip steps whose outputs exist
#   tiles/run.sh --force   # rebuild from scratch
#   tiles/run.sh --gates   # only run gate checks against current artifacts
#
# Requires:
#   - python3.11+ with rasterio, numpy, matplotlib, pandas, pyarrow,
#     xgboost, scipy, scikit-learn installed
#   - tippecanoe (apt install tippecanoe)
#   - pmtiles CLI (https://github.com/protomaps/go-pmtiles releases)
#   - GDAL 3.x (apt install gdal-bin)
#   - data/raw/naturalearth/ne_50m_land.shp (auto-downloaded)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
INTER=tiles/intermediate
SCR=tiles/scripts

FORCE=0
GATES_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --gates) GATES_ONLY=1 ;;
        *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
done

mkdir -p "$INTER" data/raw/naturalearth

skip_if_exists() {
    local out=$1
    if [ "$FORCE" = 0 ] && [ -e "$out" ]; then
        echo "  [skip] $out exists"
        return 0
    fi
    return 1
}

bar() { echo; echo "═════════════════════════════════════════════════════════════════"; echo "$@"; echo "═════════════════════════════════════════════════════════════════"; }

if [ "$GATES_ONLY" = 0 ]; then
    # Pre-step: ensure Natural Earth land polygons are present
    if [ ! -f data/raw/naturalearth/ne_50m_land.shp ]; then
        bar "Pre-step: download Natural Earth 50m land polygons"
        curl -sL https://naciscdn.org/naturalearth/50m/physical/ne_50m_land.zip \
            -o data/raw/naturalearth/ne_50m_land.zip
        (cd data/raw/naturalearth && unzip -o ne_50m_land.zip > /dev/null)
    fi
    if ! skip_if_exists "$INTER/land_mask.tif"; then
        bar "Pre-step: rasterize land mask"
        gdal_rasterize -burn 1 -init 0 -tr 0.05 0.05 \
            -te 25.0 -10.0 180.0 80.0 -ot Byte -a_srs EPSG:4326 \
            data/raw/naturalearth/ne_50m_land.shp \
            "$INTER/land_mask.tif" 2>&1 | tail -2
    fi

    # Phase 0
    if ! skip_if_exists data/outputs/hero_climate_npp_asia_anomaly.parquet; then
        bar "Phase 0: regenerate F+NPP anomaly parquet"
        python3 "$SCR/phase0_regenerate_anomaly.py"
    fi

    # Phase 1
    if ! skip_if_exists "$INTER/asia_anomaly_base.tif"; then
        bar "Phase 1: base raster"
        python3 "$SCR/phase1_base_raster.py"
    fi

    # Phase 2
    if ! skip_if_exists "$INTER/asia_anomaly_preview.png"; then
        bar "Phase 2: visual preview"
        python3 "$SCR/phase2_visual_preview.py"
    fi

    # Phase 3
    if ! skip_if_exists "$INTER/zoom6.png"; then
        bar "Phase 3: zoom rasters"
        python3 "$SCR/phase3_zoom_rasters.py"
    fi

    # Phase 4
    if ! skip_if_exists tiles/mshi_f_npp_anomaly.pmtiles; then
        bar "Phase 4: PMTiles packaging"
        bash "$SCR/phase4_build_pmtiles.sh"
    fi

    # Phase 5 (always re-run, depends on running server)
    bar "Phase 5: end-to-end render test (local pmtiles serve)"
    pmtiles serve tiles/ --port=8765 --cors='*' > /tmp/pmtiles-serve.log 2>&1 &
    SRVPID=$!
    trap "kill $SRVPID 2>/dev/null || true" EXIT
    until curl -fs http://localhost:8765/mshi_f_npp_anomaly/0/0/0.png -o /dev/null; do sleep 0.3; done
    python3 "$SCR/phase5_render_test.py"
    kill $SRVPID 2>/dev/null || true
    trap - EXIT

    # Phase 6: regenerate tilejson + viewer
    if ! skip_if_exists tiles/tilejson.json; then
        bar "Phase 6: TileJSON + viewer"
        python3 "$SCR/phase6_tilejson.py"
    fi
fi

# Gates
bar "Running all gates"
ANY_FAIL=0
for g in 0 1 2 3 4 5 6; do
    echo
    if ! python3 "$SCR/gate${g}_check.py"; then
        ANY_FAIL=1
    fi
done

if [ "$ANY_FAIL" = 1 ]; then
    echo
    echo "❌ One or more gates failed. See tiles/intermediate/gate*_results.json"
    exit 1
fi
echo
echo "✅ All gates passed."
