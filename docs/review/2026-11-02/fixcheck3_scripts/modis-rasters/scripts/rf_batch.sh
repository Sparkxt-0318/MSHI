#!/bin/bash
# Runs ee07832 (old) and de236d0 (head) LockedTest at full locked settings on synthetic tables, 2 lanes.
SCR=fixcheck3_scripts/modis-rasters
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
PY="/home/user/MSHI/.venv/bin/python -I -B"
cd $SCR/rf
run() { local t0=$(date +%s); $PY $SCR/scripts/run_lt.py $1 data/$2 out/$3 2>>out/lane_$4.log; echo "$1 $2 -> $3 rc=$? $(( $(date +%s)-t0 ))s" >> out/lane_$4.log; }
( run old V1_ols.parquet old_V1.json A; run head V1_ols.parquet head_V1.json A; run head V2_rf.parquet head_V2b.json A ) &
( run old V2_rf.parquet old_V2.json B; run head V2_rf.parquet head_V2.json B; run old V2_rf.parquet old_V2b.json B ) &
wait
echo ALLDONE >> out/lane_A.log
