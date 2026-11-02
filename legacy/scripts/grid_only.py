"""Sample only the Asia 5km prediction grid (skips already-written point tables)."""
from pathlib import Path
import sys, yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extract_features_real import build_asia_grid, finalize_features

cfg = yaml.safe_load((ROOT / "configs" / "mshi_geo.yaml").read_text())
asia_bbox = cfg["regions"]["asia"]["bounds"]
out = ROOT / cfg["paths"]["asia_grid_5km"]
grid = build_asia_grid(ROOT / cfg["paths"]["raw"], asia_bbox,
                       cfg["grid"]["iteration_deg"])
grid = finalize_features(grid)
grid.to_parquet(out, index=False)
print(f"Wrote {len(grid)} cells → {out}")
