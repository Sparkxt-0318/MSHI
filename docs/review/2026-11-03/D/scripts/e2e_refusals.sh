#!/bin/bash
# Area D end-to-end, step 5: every Phase-2 stage refuses missing or changed inputs (runner level, sandbox).
# Each case changes one input, runs the stages through the entry point, prints the run-log statuses, and restores
# the input byte for byte. Usage: e2e_refusals.sh <D>
D=$1
SB=$D/e2e/sb
CFG=$D/e2e/v3_sandbox.yaml
PY="/home/user/MSHI/.venv/bin/python -I -B"
RUN="$PY $D/scripts/run_mshi.py --config $CFG"
show() {  # last N run-log records: stage, status
  $PY -c "import json,sys; L=open('$SB/results/run_log.jsonl').read().splitlines()[-$1:]
for l in L:
    r=json.loads(l); print('   ', r['stage'], '|', r['status'][:140], '| exploratory', r.get('exploratory'))"
}
mutate() {  # rewrite a parquet with the first numeric column +0.1 in the first row
  $PY -c "
import pandas as pd, sys
p=sys.argv[1]; d=pd.read_parquet(p); c=sys.argv[2]; d.loc[d.index[0], c]=d.loc[d.index[0], c]+0.1; d.to_parquet(p, index=False)" $1 $2
}
echo "== R1: results/features_analysis.json missing"
mv $SB/results/features_analysis.json $D/tmp/features_analysis.json.bak
$RUN --stage transfer_matrix --stage within_continent --stage aoa_sensitivity --stage us_r2 > $D/logs/e2e_R1.log 2>&1; echo "   exit=$?"
show 4
mv $D/tmp/features_analysis.json.bak $SB/results/features_analysis.json

echo "== R2: interim/features_analysis_qc.parquet changed after its run"
cp -p $SB/interim/features_analysis_qc.parquet $D/tmp/fa_qc.bak
mutate $SB/interim/features_analysis_qc.parquet log_rs
$RUN --stage transfer_matrix --stage within_continent --stage aoa_sensitivity --stage us_r2 > $D/logs/e2e_R2.log 2>&1; echo "   exit=$?"
show 4
cp -p $D/tmp/fa_qc.bak $SB/interim/features_analysis_qc.parquet

echo "== R2b: interim/features_analysis_repo.parquet changed (read only by us_r2)"
cp -p $SB/interim/features_analysis_repo.parquet $D/tmp/fa_repo.bak
mutate $SB/interim/features_analysis_repo.parquet log_rs
$RUN --stage us_r2 > $D/logs/e2e_R2b.log 2>&1; echo "   exit=$?"
show 1
cp -p $D/tmp/fa_repo.bak $SB/interim/features_analysis_repo.parquet

echo "== R3: interim/transfer_predictions_qc.parquet changed after its run"
cp -p $SB/interim/transfer_predictions_qc.parquet $D/tmp/tp.bak
mutate $SB/interim/transfer_predictions_qc.parquet pred_log
$RUN --stage within_continent > $D/logs/e2e_R3.log 2>&1; echo "   exit=$?"
show 1
cp -p $D/tmp/tp.bak $SB/interim/transfer_predictions_qc.parquet

echo "== R4: derived/records_analysis.parquet changed after its run"
cp -p $SB/derived/records_analysis.parquet $D/tmp/rec.bak
mutate $SB/derived/records_analysis.parquet log_rs
$RUN --stage noise_ceiling --stage us_r2 > $D/logs/e2e_R4.log 2>&1; echo "   exit=$?"
show 2
cp -p $D/tmp/rec.bak $SB/derived/records_analysis.parquet

echo "== R5: fetch_worldclim raster replaced (within_continent and aoa read the climate grid)"
T=$SB/raw/worldclim/2.1/2.5m/wc2.1_2.5m_bio_1.tif
cp -p $T $D/tmp/bio1.bak
printf 'x' >> $T
$RUN --stage within_continent --stage aoa_sensitivity > $D/logs/e2e_R5.log 2>&1; echo "   exit=$?"
show 2
cp -p $D/tmp/bio1.bak $T

echo "== R6: another config (phase2.bootstrap.n + 1)"
$PY -c "
import yaml; d=yaml.safe_load(open('$CFG')); d['phase2']['bootstrap']['n'] += 1
open('$D/tmp/v3_sandbox_n201.yaml','w').write(yaml.safe_dump(d, sort_keys=False))"
$PY $D/scripts/run_mshi.py --config $D/tmp/v3_sandbox_n201.yaml --stage us_r2 --stage noise_ceiling > $D/logs/e2e_R6.log 2>&1; echo "   exit=$?"
show 2
$PY -c "
import sys; sys.path.insert(0, '/home/user/MSHI')
from mshi.config import load_config
from mshi.analysis.us_r2 import us_r2
try:
    us_r2(load_config('$D/tmp/v3_sandbox_n201.yaml')); print('   direct us_r2 call: RAN (no refusal)')
except Exception as e:
    print('   direct us_r2 call refused:', type(e).__name__, str(e)[:160])"
