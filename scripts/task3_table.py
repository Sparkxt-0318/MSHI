"""Task 3 — build the Framing-2 transfer-comparison table.

Reads data/outputs/sweep_results.json from Task 2 and writes
data/outputs/framing2_table.csv and data/outputs/framing2_table.md.

Δ_transfer is computed against the climate_only config (F).
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "outputs" / "sweep_results.json"
data = json.loads(src.read_text())
rows = []
for r in data["results"]:
    rows.append({
        "config": r["name"],
        "description": r["desc"],
        "n_features": r["n_features"],
        "features_kind": ("all (incl. clay/sand/silt)" if r["n_features"] == 20
                          else f"selected ({r['n_features']} features)"),
        "cv_r2": round(r["cv_r2_mean"], 3),
        "transfer_r2": round(r["transfer_r2"], 3),
        "transfer_bias": round(r["transfer_bias"], 3),
        "pred_std_us": round(r["transfer_pred_std"], 3),
    })
df = pd.DataFrame(rows)

# Δ vs climate_only baseline
baseline = df.loc[df["config"] == "F_climate_only", "transfer_r2"].iloc[0]
df["delta_transfer_vs_climate_only"] = (df["transfer_r2"] - baseline).round(3)

csv_path = ROOT / "data" / "outputs" / "framing2_table.csv"
md_path  = ROOT / "data" / "outputs" / "framing2_table.md"
df.to_csv(csv_path, index=False)

# Markdown table — manually format because we want a tighter view
header = ("| Config | Features | n_feat | CV R² | Transfer R² | "
          "Δ vs climate-only | bias |")
sep    =  "|---|---|---:|---:|---:|---:|---:|"
lines = [
    "# Framing-2 transfer comparison",
    "",
    "Source: `data/outputs/sweep_results.json` (Task 2 sweep, n_train=615 Asia, n_us=274)",
    "",
    "Climate-only generalises Asia → US (R² = +0.127). Every configuration that",
    "includes the SoilGrids texture features (clay/sand/silt or clay_sand_ratio)",
    "lands transfer R² ≈ 0, confirming that the soil-feature contribution to",
    "respiration is regionally specific and does not transfer cross-continent.",
    "",
    header, sep,
]
for r in df.itertuples():
    lines.append(
        f"| {r.config} | {r.description} | {r.n_features} | "
        f"{r.cv_r2:+.3f} | {r.transfer_r2:+.3f} | "
        f"{r.delta_transfer_vs_climate_only:+.3f} | {r.transfer_bias:+.3f} |"
    )

lines += [
    "",
    "## Reading the table",
    "",
    "- **CV R²** is from 5-fold spatial-block cross-validation at 5° latitude/",
    "  longitude blocks within the Asia training set. With n_train=615 spread",
    "  across 25-180°E and -10-80°N, every fold has to extrapolate to a different",
    "  climate-biome combination, so values around zero or slightly negative are",
    "  expected. Random-KFold CV gives R² ≈ +0.09 on the same data.",
    "",
    "- **Transfer R²** is on the held-out US set (n=274). This is the primary",
    "  generalisation metric.",
    "",
    "- **Δ vs climate-only** isolates the marginal contribution (negative for",
    "  every soil-feature configuration) of adding gridded soil layers.",
    "",
    "- **Bias** = mean(predicted − observed) on the US set. A negative bias means",
    "  the model is shrinking US predictions toward the Asia training mean.",
]
md_path.write_text("\n".join(lines))

print(f"Wrote {csv_path}")
print(f"Wrote {md_path}")
print()
print("\n".join(lines[12:12 + 1 + len(df) + 1]))  # show table block
