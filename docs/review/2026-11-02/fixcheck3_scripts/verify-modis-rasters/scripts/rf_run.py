"""Run the full locked LockedTest of a package copy on a SYNTHETIC table. usage: rf_run.py {old,head} FEAT OUT
old = git archive ee07832, head = git archive HEAD (mshi identical to a6c00bc). Locked settings unchanged;
head verifies the lock against its own archived docs/handoff and configs."""
import sys, time
V = "fixcheck3_scripts/verify-modis-rasters"
which, feat, out = sys.argv[1:4]
sys.path.insert(0, f"{V}/pkg/{which}")
import pandas as pd
import mshi
from mshi.config import load_config
from mshi.analysis import clean_test as CT
from mshi.io import write_json
assert mshi.__file__.startswith(f"{V}/pkg/{which}/"), mshi.__file__
cfg = load_config()
lt = CT.LockedTest(cfg)
print("lock:", getattr(lt, "lock", None) is not None, "rf:", cfg["clean_test"]["locked"].get("rf"), file=sys.stderr)
d = pd.read_parquet(feat)
t = time.time()
R = lt.run(d)
print(f"{which} {feat.rsplit('/',1)[-1]}: selected {R['selected']['set']}/{R['selected']['learner']} in {time.time()-t:.0f}s",
      file=sys.stderr)
write_json(R, out)
