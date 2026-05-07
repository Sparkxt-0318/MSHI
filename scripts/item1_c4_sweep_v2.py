"""Item 1 Checkpoint 4 — combined sweep_results_v2.json.

Merges Run A's 6 configurations (sweep_results.json) with the two new
MODIS configurations (F+NPP, Full+MODIS) into one document. Keeps the
v1 file untouched.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"

runA = json.load(open(OUT / "sweep_results.json"))
fnpp_metrics = json.load(open(OUT / "F_NPP_metrics.json"))
fnpp_shap    = json.load(open(OUT / "F_NPP_shap.json"))
full_metrics = json.load(open(OUT / "Full_MODIS_metrics.json"))
full_shap    = json.load(open(OUT / "Full_MODIS_shap.json"))


def make_entry(metrics, shap_doc, ci_excludes_zero, transfer_ci_low, transfer_ci_high, notes):
    return {
        "name": metrics["config_name"],
        "desc": notes,
        "n_features": metrics["n_features"],
        "features": metrics["features"],
        "params": metrics["params"],
        "n_train": metrics["n_train"],
        "n_us": metrics["n_us"],
        "cv_r2_mean": metrics["cv"]["mean_r2"],
        "cv_r2_per_fold": metrics["cv"]["per_fold_r2"],
        "cv_rmse_mean": metrics["cv"]["mean_rmse"],
        "transfer_r2": metrics["transfer"]["r2"],
        "transfer_rmse": metrics["transfer"]["rmse_log"],
        "transfer_mae": metrics["transfer"]["mae_log"],
        "transfer_bias": metrics["transfer"]["bias"],
        "transfer_pred_std": metrics["transfer"]["pred_std"],
        "transfer_obs_std": metrics["transfer"]["obs_std"],
        "transfer_spearman": metrics["transfer"]["spearman"],
        "bootstrap_n": metrics["transfer"]["bootstrap_n"],
        "bootstrap_median": metrics["transfer"]["bootstrap_median"],
        "bootstrap_ci_low": transfer_ci_low,
        "bootstrap_ci_high": transfer_ci_high,
        "bootstrap_ci_excludes_zero": ci_excludes_zero,
        "shap_top5": [(r["feature"], r["mean_abs_shap"]) for r in shap_doc["ranking"][:5]],
    }


fnpp_entry = make_entry(
    fnpp_metrics, fnpp_shap,
    fnpp_metrics["transfer"]["ci_excludes_zero"],
    fnpp_metrics["transfer"]["ci_low"],
    fnpp_metrics["transfer"]["ci_high"],
    "8 bioclim + 4 MODIS continuous (npp, lst_day, lst_night, lst_diurnal_range). "
    "Run A F hyperparameters."
)
full_entry = make_entry(
    full_metrics, full_shap,
    full_metrics["transfer"]["ci_excludes_zero"],
    full_metrics["transfer"]["ci_low"],
    full_metrics["transfer"]["ci_high"],
    "20 prior + 4 MODIS continuous + 10 IGBP one-hot. "
    "Run A B hyperparameters."
)

# Build combined v2 document. Preserve Run A entries verbatim, append new ones.
v2 = {
    "schema_version": "v2 (Run A + Item 1 MODIS)",
    "asia_n": runA.get("asia_n"),
    "us_n":   runA.get("us_n"),
    "results": list(runA["results"]) + [fnpp_entry, full_entry],
}

(OUT / "sweep_results_v2.json").write_text(json.dumps(v2, indent=2))
print(f"wrote sweep_results_v2.json with {len(v2['results'])} configs")

# Also write a compact comparison table to markdown
md = ["# Sweep results — v1 (Run A) + v2 (Item 1 MODIS) combined",
      "",
      "| Config | Features | n_train | n_us | CV R² | Transfer R² | 95% CI | CI excl. 0 |",
      "|---|---:|---:|---:|---:|---:|---|---|"]
for c in v2["results"]:
    name = c["name"]
    nf = c["n_features"]
    n_train = c.get("n_train", "—")
    n_us = c.get("n_us", "—")
    cv = c.get("cv_r2_mean")
    tr = c.get("transfer_r2")
    cl = c.get("bootstrap_ci_low")
    ch = c.get("bootstrap_ci_high")
    excl = c.get("bootstrap_ci_excludes_zero")
    cv_s = f"{cv:+.3f}" if isinstance(cv, (int, float)) else "—"
    tr_s = f"{tr:+.3f}" if isinstance(tr, (int, float)) else "—"
    ci_s = f"({cl:+.3f}, {ch:+.3f})" if isinstance(cl, (int, float)) else "—"
    excl_s = "**yes**" if excl is True else ("no" if excl is False else "—")
    md.append(f"| {name} | {nf} | {n_train} | {n_us} | {cv_s} | {tr_s} | {ci_s} | {excl_s} |")

(OUT / "sweep_results_v2_table.md").write_text("\n".join(md))
print(f"wrote sweep_results_v2_table.md")

# Print to stdout
print()
print("\n".join(md))
