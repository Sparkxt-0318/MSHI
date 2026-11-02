import sys, copy, json, hashlib
root, cfgpath, table, out, which = sys.argv[1:6]
sys.path.insert(0, root)
import pandas as pd
from mshi.config import load_config
from mshi.analysis import clean_test as CT
from mshi.io import write_json
cfg = load_config(cfgpath)
lt = CT.LockedTest(cfg, require_lock=False) if which == "new" else CT.LockedTest(cfg)
L = copy.deepcopy(lt.L)
L["rf"]["n_estimators"] = 60; L["xgb"]["n_estimators"] = 60
L["bootstrap_n"] = 200; L["seed_spread"] = [0, 2]
lt.L = L
d = pd.read_parquet(table)
R = lt.run(d)
write_json(R, out)
print(which, table.rsplit("/", 1)[-1], R["selected"]["set"], R["selected"]["learner"], hashlib.sha256(open(out, "rb").read()).hexdigest()[:12])
