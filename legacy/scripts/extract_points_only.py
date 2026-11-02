"""Re-extract feature columns at training and US validation points only.
Skip the 5km Asia grid (slow, unchanged when only points table changes).
"""
import sys
from pathlib import Path
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extract_features_real import extract_points_region, finalize_features  # noqa: E402

cfg = yaml.safe_load((ROOT / "configs" / "mshi_geo.yaml").read_text())
raw_dir = ROOT / cfg["paths"]["raw"]
proc = ROOT / cfg["paths"]["processed"]

points = pd.read_parquet(proc / "respiration_points.parquet")
print(f"points: {len(points)} total  (asia={(points.region=='asia').sum()} "
      f"us={(points.region=='us').sum()} other={(points.region=='other').sum()})")

asia_pts = points[points["region"] == "asia"].reset_index(drop=True)
us_pts = points[points["region"] == "us"].reset_index(drop=True)

asia_feat = finalize_features(extract_points_region(asia_pts, raw_dir, region="asia"))
us_feat = finalize_features(extract_points_region(us_pts, raw_dir, region="us"))

asia_feat.to_parquet(ROOT / cfg["paths"]["feature_table_train"], index=False)
us_feat.to_parquet(ROOT / cfg["paths"]["feature_table_us"], index=False)

print(f"Wrote {len(asia_feat)} Asia training rows and {len(us_feat)} US validation rows")
print(f"  source breakdown (asia): {dict(asia_feat['source'].value_counts())}")
print(f"  source breakdown (us):   {dict(us_feat['source'].value_counts())}")
