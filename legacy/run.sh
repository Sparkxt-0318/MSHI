#!/usr/bin/env bash
# run.sh — MSHI-Geo end-to-end pipeline (v2: soil respiration target).
#
# Modes:
#   bash run.sh demo         Synthetic smoke test (no internet, ~30 sec)
#   bash run.sh download     Pull all data sources / print instructions
#   bash run.sh build_target Build training points from COSORE+SRDB
#   bash run.sh extract      Extract features at training points + grid cells
#   bash run.sh train        Train MSHI-Geo on real Asian data
#   bash run.sh validate     Run Asia → US transfer test
#   bash run.sh predict5km   Predict on 5 km Asia grid + composite anomaly
#   bash run.sh predict1km   Predict on 1 km Asia grid (slower)
#   bash run.sh hero         Render the hero map from latest 5km composite
#   bash run.sh hero1km      Render the hero map at 1km resolution
#   bash run.sh all          Full real-data pipeline (after data is downloaded)

set -e
set -u
cd "$(dirname "$0")"

CONFIG="configs/mshi_geo.yaml"

case "${1:-demo}" in
    demo)
        echo "▶ Running synthetic smoke test..."
        python src/demo_synthetic.py
        ;;
    download)
        echo "▶ Pulling data sources..."
        python src/download.py --target all
        ;;
    build_target)
        echo "▶ Building training points from SRDB+COSORE..."
        python src/build_target.py
        ;;
    extract)
        echo "▶ Extracting features at training points and grid cells..."
        python src/extract_features_real.py --config "$CONFIG"
        ;;
    train)
        echo "▶ Training MSHI-Geo..."
        python src/train.py --config "$CONFIG"
        ;;
    validate)
        echo "▶ Running Asia → US transfer validation..."
        python src/validate.py --config "$CONFIG"
        ;;
    predict5km)
        echo "▶ Predicting on 5 km Asia grid..."
        python src/predict.py --config "$CONFIG" --resolution 5km
        python src/composite.py --config "$CONFIG" \
            --predictions data/processed/asia_grid_5km_predictions.parquet
        ;;
    predict1km)
        echo "▶ Predicting on 1 km Asia grid (this takes a while)..."
        python src/predict.py --config "$CONFIG" --resolution 1km
        python src/composite.py --config "$CONFIG" \
            --predictions data/processed/asia_grid_1km_predictions.parquet
        ;;
    hero)
        echo "▶ Rendering hero map (5km)..."
        python src/hero_map.py \
            --composite data/processed/asia_grid_5km_predictions_anomaly.parquet
        ;;
    hero1km)
        echo "▶ Rendering hero map (1km)..."
        python src/hero_map.py \
            --composite data/processed/asia_grid_1km_predictions_anomaly.parquet
        ;;
    all)
        echo "▶ Full real-data pipeline"
        bash "$0" build_target
        bash "$0" extract
        bash "$0" train
        bash "$0" validate
        bash "$0" predict5km
        bash "$0" hero
        echo "✓ Pipeline complete. Hero map → data/outputs/hero_mshi_geo_asia.png"
        ;;
    *)
        echo "Unknown mode: $1"
        echo "Usage: bash run.sh [demo|download|build_target|extract|train|validate|predict5km|predict1km|hero|hero1km|all]"
        exit 1
        ;;
esac
