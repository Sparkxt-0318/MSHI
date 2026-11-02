"""Match the committed SRDB-derived sites back to SRDB rows and audit selection filters."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

REPO, SRDB, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
s = pd.read_csv(SRDB, low_memory=False)
R = {"srdb_rows": len(s)}
# Replicate build_target.load_srdb filters
f = s.dropna(subset=["Latitude", "Longitude", "Rs_annual"])
f = f[(f.Rs_annual >= 50) & (f.Rs_annual <= 4500)]
f = f[f.Manipulation.isin(["None", "Control", "control"]) | f.Manipulation.isna()]
R["after_repo_filters"] = len(f)
R["manipulation_values_kept"] = f.Manipulation.fillna("NA").value_counts().head(5).to_dict()

asia = pd.read_parquet(REPO / "data/processed/training_features_v2.parquet").assign(set="asia")
us = pd.read_parquet(REPO / "data/processed/us_validation_features_v2.parquet").assign(set="us")
sites = pd.concat([asia, us])
sites = sites[sites.source == "srdb"].copy()
# recover SRDB row: site_id = 'srdb_<index after filtering & reset_index>'
sites["row"] = sites.site_id.str.replace("srdb_", "").astype(int)
fr = s  # site_id carries the ORIGINAL csv row index (assigned before reset_index)
ok = sites.row < len(fr)
m = sites[ok].join(fr, on="row", rsuffix="_srdb")
coord_match = (np.isclose(m.latitude, m.Latitude) & np.isclose(m.longitude, m.Longitude))
R["n_srdb_sites"] = int(len(sites)); R["index_matched_with_same_coords"] = int(coord_match.sum())
m = m[coord_match]
m["rs_match"] = np.isclose(m.rs_annual, m.Rs_annual)
R["rs_value_matches"] = int(m.rs_match.sum())

def tab(col):
    return {k: m[m.set == k][col].fillna("NA").astype(str).value_counts().head(12).to_dict() for k in ["asia", "us"]}
for col in ["Meas_method", "Quality_flag", "Ecosystem_type", "Ecosystem_state", "Biome", "Duplicate_record", "Country"]:
    R[col] = tab(col)
R["Annual_coverage_lt_0.75"] = {k: int((m[m.set == k].Annual_coverage < 0.75).sum()) for k in ["asia", "us"]}
R["Annual_coverage_missing"] = {k: int(m[m.set == k].Annual_coverage.isna().sum()) for k in ["asia", "us"]}
R["Study_midyear"] = {k: m[m.set == k].Study_midyear.describe()[["min", "25%", "50%", "75%", "max"]].round(1).to_dict() for k in ["asia", "us"]}
R["has_Duplicate_record_flag"] = {k: int(m[m.set == k].Duplicate_record.notna().sum()) for k in ["asia", "us"]}
alk = m.Meas_method.fillna("").str.contains("Alkali|Soda|lime|absorption", case=False)
R["alkali_or_sodalime"] = {k: int(alk[m.set == k].sum()) for k in ["asia", "us"]}
qbad = m.Quality_flag.fillna("").str.contains("Q1[0-9]", regex=True)
R["quality_flag_Q1x"] = {k: int(qbad[m.set == k].sum()) for k in ["asia", "us"]}
# how many SRDB rows per retained site location (multi-year records collapsed to one)
ff = f.copy(); ff["cell"] = list(zip((ff.Longitude / 0.05).round().astype(int), (ff.Latitude / 0.05).round().astype(int)))
cnt = ff.cell.value_counts()
m["cell"] = list(zip((m.longitude / 0.05).round().astype(int), (m.latitude / 0.05).round().astype(int)))
m["records_in_cell"] = m.cell.map(cnt)
R["srdb_records_per_retained_cell"] = {k: m[m.set == k].records_in_cell.describe()[["50%", "75%", "max"]].to_dict() for k in ["asia", "us"]}
R["retained_cells_with_gt1_record"] = {k: int((m[m.set == k].records_in_cell > 1).sum()) for k in ["asia", "us"]}
(OUT / "srdb_audit.json").write_text(json.dumps(R, indent=1, default=str))
print(json.dumps(R, indent=1, default=str))
