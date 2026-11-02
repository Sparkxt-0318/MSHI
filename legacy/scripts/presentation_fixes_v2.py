"""Presentation fixes — round 2:
  - Add distinguishing model_label / model_subtitle to the two existing heroes
  - Apply a 0.01°-tolerance Douglas-Peucker simplification to country borders
    to clean up the Saudi/UAE/Oman hairline border artifact

No model retraining — re-uses the anomaly parquets already on disk.
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hero_map import render_hero_map  # noqa: E402

OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"

# Same metadata that's already encoded in the existing heroes (Run-A, post-fix)
common = dict(n_train=615, n_us=274, resolution_km="~5")
F_meta = dict(cv_r2=-0.067, transfer_r2=0.127, **common)
B_meta = dict(cv_r2=-0.083, transfer_r2=0.020, **common)

print("re-rendering hero_climate_only_asia (CLIMATE-ONLY MODEL) ...")
df_F = pd.read_parquet(PROC / "hero_climate_only_asia_anomaly.parquet")
render_hero_map(
    df_F,
    OUT / "hero_climate_only_asia.png",
    OUT / "hero_climate_only_asia.pdf",
    OUT / "hero_climate_only_asia_screen.png",
    metadata=F_meta,
    model_label="CLIMATE-ONLY MODEL",
    model_subtitle="Climate-feature model — transfers to held-out US sites",
)

print("re-rendering hero_full_features_asia (FULL FEATURE STACK) ...")
df_B = pd.read_parquet(PROC / "hero_full_features_asia_anomaly.parquet")
render_hero_map(
    df_B,
    OUT / "hero_full_features_asia.png",
    OUT / "hero_full_features_asia.pdf",
    OUT / "hero_full_features_asia_screen.png",
    metadata=B_meta,
    model_label="FULL FEATURE STACK",
    model_subtitle="Climate + soil features — Asia-specific structure does not transfer",
)
print("done.")
