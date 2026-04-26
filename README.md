# MSHI-Geo: Continental-Scale Soil Microbial Respiration for Asia

Geospatial twin of the published electrochemical MSHI biosensor. Predicts
soil respiration at 1 km resolution across Asia from environmental
features, validated cross-continentally on a US held-out subset.

## Scientific framing

Soil microbial respiration is the biological flux your EAB biosensor
measures (electron transfer ∝ metabolic activity ∝ substrate oxidation).
This project predicts the same flux from satellite-derived and gridded
environmental features at continental scale, then composes a
**climate-corrected anomaly score** isolating soil-driven variation
from climate-driven variation.

The pitch: *the same biological signal at three scales — electrochemical
(centimeter), chamber (meter), satellite-derived (kilometer).*

## Pipeline

```
build_target → extract → train → validate → predict → composite → hero_map
```

One command: `bash run.sh all` (after data downloaded).

## Quick start

```bash
# 1. Install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Smoke test (no internet, ~30 sec)
bash run.sh demo

# 3. Pull real data (~2-4 hours wall-clock, mostly waiting)
bash run.sh download   # SoilGrids automated; instructions for everything else

# 4. After data arrives:
bash run.sh all
```

## Outputs

```
data/outputs/
├── hero_mshi_geo_asia.png           ← Hero map (300 DPI, poster)
├── hero_mshi_geo_asia.pdf           ← Vector for poster
├── hero_mshi_geo_asia_screen.png    ← Slide deck (160 DPI)
├── mshi_geo_xgb.json                ← Trained model
├── training_metrics.json            ← Spatial CV results, SHAP rankings
├── validation_report.json           ← Asia → US transfer numbers
├── shap_summary.png                 ← Interpretability
└── *.tif                            ← GeoTIFFs (open in QGIS)
```

## Modules

| File | Purpose |
|---|---|
| `download.py` | Stage all data sources (SoilGrids automated; others with instructions) |
| `build_target.py` | Build training points from COSORE + SRDB |
| `features.py` | Sample raster features at points and across grid |
| `train.py` | XGBoost + spatial-block CV + SHAP |
| `validate.py` | Asia → US external validation |
| `predict.py` | Chunked inference at 5km or 1km |
| `composite.py` | Climate-baseline + anomaly ratio |
| `hero_map.py` | Bedrock-style hero visual (PNG + PDF) |
| `demo_synthetic.py` | End-to-end smoke test |

See `CLAUDE_CODE_PROMPT.md` for a ready-to-paste Claude Code instruction set.
