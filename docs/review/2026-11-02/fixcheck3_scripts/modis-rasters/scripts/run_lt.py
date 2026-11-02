"""Run the full locked LockedTest of a package copy (git archive in scratch) on a SYNTHETIC feature table.
usage: run_lt.py {old,head} FEATURES OUT_JSON
old = ee07832 (RF predicted with n_jobs=2), head = de236d0 (== a6c00bc for mshi/; RF predicted with 1 thread).
Locked settings unchanged; head verifies the real lock (files read from its own archive copy).
Adapted from docs/review/2026-11-02/fixcheck_scripts/verify-fidelity2/c3/run_lt.py (force_rf dropped)."""
import sys, time
SCR = "fixcheck3_scripts/modis-rasters"
which, feat, out = sys.argv[1:4]
sys.path.insert(0, f"{SCR}/pkg/{which}")
import pandas as pd
import mshi
from mshi.config import load_config
from mshi.analysis import clean_test as CT
from mshi.io import write_json
assert mshi.__file__.startswith(f"{SCR}/pkg/{which}/"), mshi.__file__
cfg = load_config()
lt = CT.LockedTest(cfg)
d = pd.read_parquet(feat)
t = time.time()
R = lt.run(d)
print(f"{which} {feat.rsplit('/', 1)[-1]}: mshi from {mshi.__file__}; selected {R['selected']['set']}/"
      f"{R['selected']['learner']} in {time.time() - t:.0f}s", file=sys.stderr)
write_json(R, out)
