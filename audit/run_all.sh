#!/usr/bin/env bash
# Run the audit pipeline in order from the repository root:
#   bash audit/run_all.sh [first_step]
# e.g. `bash audit/run_all.sh 23` to start at the site table. Logs go to audit/outputs/logs/.
# Step 20 (WorldClim download, 4.5 GB) runs only if the rasters are missing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-/home/user/venv-mshi/bin/python}"
FIRST="${1:-20}"
mkdir -p audit/outputs/logs audit/outputs/a1 audit/outputs/a2 audit/outputs/a3
STEPS=(20_fetch_worldclim30s 21_cosore_annual 22_country_check 23_build_site_table 32_a3_overlap 33_a3_issue_draft
       24_a1_transfer 25_a1_coverage 26_a1_modis 27_a2_ceiling 28_a3_effect 31_a1_tuning_sensitivity
       36_a1_foldseed_sensitivity 29_crossref_check 34_tables 30_figures)
for s in "${STEPS[@]}"; do
  n="${s%%_*}"
  if [ "$n" -lt "$FIRST" ] && [ "$n" -ne 32 ] && [ "$n" -ne 33 ]; then continue; fi
  if [ "$FIRST" -gt 23 ] && { [ "$n" -eq 32 ] || [ "$n" -eq 33 ]; }; then continue; fi
  if [ "$n" = "20" ]; then
    if [ -f data/raw/worldclim30s/wc2.1_30s_bio_17.tif ]; then continue; fi
    "$PY" -I "audit/$s.py" data/raw/worldclim30s > "audit/outputs/logs/$s.log" 2>&1
    continue
  fi
  echo "$(date -u +%H:%M:%S) start $s"
  "$PY" -I "audit/$s.py" > "audit/outputs/logs/$s.log" 2>&1
  echo "$(date -u +%H:%M:%S) done  $s"
done
echo "ALL_DONE"
