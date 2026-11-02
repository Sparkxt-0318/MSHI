#!/bin/bash
# verifier's RF batch: ee07832 (old) vs HEAD (== a6c00bc mshi) LockedTest at full locked settings, 2 lanes.
V=fixcheck3_scripts/verify-modis-rasters
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
PY="/home/user/MSHI/.venv/bin/python -I -B"
cd $V/rf
run() { local t0=$(date +%s); $PY $V/scripts/rf_run.py $1 data/$2 out/$3 2>>out/lane_$4.log; echo "$1 $2 -> $3 rc=$? $(( $(date +%s)-t0 ))s" >> out/lane_$4.log; }
( run old V2_rf.parquet old_V2a.json A; run head V2_rf.parquet head_V2.json A; run old W3_rf.parquet old_W3.json A ) &
( run old V2_rf.parquet old_V2b.json B; run old V2_rf.parquet old_V2c.json B; run head W3_rf.parquet head_W3.json B ) &
wait
echo ALLDONE >> out/lane_A.log
