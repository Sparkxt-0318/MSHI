"""Phase 1 of atlas-figure-regen-2026:
re-render hero_full_features_asia using Full+MODIS predictions from
data/outputs/atlas_lookup.json (0.5° / ~55 km).

The previous hero_full_features_asia.{png,pdf} encoded the Run-A
"B_heavier_reg" (climate+soil, no MODIS) config — Asia→US R² = +0.020.
This regeneration replaces it with the Full+MODIS config — Asia→US
R² = +0.072, CI (-0.084, +0.189).

Why the resolution dropped from ~5 km to ~55 km: the 5 km Asia feature
grid (SoilGrids + WorldClim 5 km rasters) is not on disk on this branch.
The 0.5° Full+MODIS anomaly is available in atlas_lookup.json from the
earlier `claude/atlas-fullmodis-lookup` work and is used as-is — no
model retraining, no re-extraction.

Source-of-truth values (see PHASE_0 verification in COMMIT_NOTES.md):
  Full_MODIS_metrics.json transfer.r2     = 0.0724  → 0.072
  Full_MODIS_metrics.json transfer.ci_*   = (-0.084, +0.189)
  Full_MODIS_metrics.json cv.mean_r2      = 0.0789  → 0.079
  Full_MODIS_metrics.json n_train         = 463
  Full_MODIS_metrics.json n_us            = 223
"""
import json
import sys
import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hero_map import render_hero_map  # noqa: E402

OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"


def main() -> int:
    # Load Full+MODIS per-cell anomaly from atlas_lookup.json (0.5° grid).
    lookup = json.loads((OUT / "atlas_lookup.json").read_text())
    rows = [
        {
            "longitude": c["lon"],
            "latitude": c["lat"],
            "mshi_geo_anomaly": c["fullmodis"]["anomaly"],
        }
        for c in lookup["cells"]
        if c.get("fullmodis") is not None
    ]
    df = pd.DataFrame(rows)
    print(f"loaded {len(df):,} Full+MODIS cells at 0.5° from atlas_lookup.json")
    print(f"  anomaly median={df['mshi_geo_anomaly'].median():.3f}  "
          f"5–95% ({df['mshi_geo_anomaly'].quantile(.05):.3f}, "
          f"{df['mshi_geo_anomaly'].quantile(.95):.3f})")

    # Persist the anomaly parquet alongside the F+NPP one, for reproducibility.
    anom_path = PROC / "hero_full_features_asia_anomaly.parquet"
    df.to_parquet(anom_path, index=False)
    print(f"wrote {anom_path}")

    # Metrics from Full_MODIS_metrics.json (source of truth).
    metrics = json.loads((OUT / "Full_MODIS_metrics.json").read_text())
    metadata = {
        "cv_r2": round(metrics["cv"]["mean_r2"], 3),       # +0.079
        "transfer_r2": round(metrics["transfer"]["r2"], 3),  # +0.072
        "n_train": metrics["n_train"],   # 463
        "n_us": metrics["n_us"],         # 223
        "resolution_km": "~55",          # 0.5° ≈ 55 km
        "date": datetime.date.today().isoformat(),
    }
    print(f"metadata: {metadata}")

    render_hero_map(
        df,
        OUT / "hero_full_features_asia.png",
        OUT / "hero_full_features_asia.pdf",
        OUT / "hero_full_features_asia_screen.png",
        metadata=metadata,
        model_label="FULL+MODIS MODEL",
        model_subtitle="Adds soil structure features — transfer drops; CI spans zero",
    )
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
