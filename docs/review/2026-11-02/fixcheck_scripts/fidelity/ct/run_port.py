"""Run LockedTest (new port from /home/user/MSHI, or old port from ./old_pkg) on a synthetic table.
usage: run_port.py {new,old} FEATURES OUT_JSON {reduced,full}"""
import copy, json, sys, time
which, feat, out, mode = sys.argv[1:5]
if which == "old":
    sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/fidelity/ct/old_pkg")
else:
    sys.path.insert(0, "/home/user/MSHI")
import pandas as pd
import mshi
from mshi.config import load_config
from mshi.analysis.clean_test import LockedTest
from mshi.io import write_json
print("mshi from", mshi.__file__, file=sys.stderr)
if which == "old":
    cfg = load_config("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/fidelity/ct/old_pkg/configs/v3.yaml")
    lt = LockedTest(cfg)
else:
    cfg = load_config()
    lt = LockedTest(cfg)                 # verifies the real lock (read-only)
if mode in ("reduced", "reduced2"):
    L = copy.deepcopy(lt.L)
    L["xgb"]["n_estimators"] = 40 if mode == "reduced" else L["xgb"]["n_estimators"]
    L["rf"]["n_estimators"] = 40
    L["bootstrap_n"] = 300
    L["seed_spread"] = [0, 3]
    lt.L = L
d = pd.read_parquet(feat)
t = time.time()
R = lt.run(d)
print(f"{which} {mode} {feat.rsplit('/',1)[-1]}: selected {R['selected']['set']}/{R['selected']['learner']} in {time.time()-t:.0f}s",
      file=sys.stderr)
write_json(R, out)
