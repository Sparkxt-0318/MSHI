"""Run the full locked LockedTest (old port ee07832 or new port HEAD) on a SYNTHETIC table.
usage: run_lt.py {old,new} FEATURES OUT_JSON [force_rf]
force_rf: selection is computed as usual, but the selected model is replaced by the best RF row, so that
primary metrics, seed spread and AOA are computed for an RF model (to see what changes if RF were selected).
Locked settings are used unchanged."""
import sys, time
HERE = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/verify-fidelity2/c3"
which, feat, out = sys.argv[1:4]
force_rf = len(sys.argv) > 4 and sys.argv[4] == "force_rf"
sys.path.insert(0, f"{HERE}/old" if which == "old" else "/home/user/MSHI")
import pandas as pd
import mshi
from mshi.config import load_config
from mshi.analysis import clean_test as CT
from mshi.io import write_json
print("mshi from", mshi.__file__, file=sys.stderr)
cfg = load_config(f"{HERE}/old/configs/v3.yaml") if which == "old" else load_config()
Base = CT.LockedTest


class LT(Base):
    def select(self, train_all):
        sel, best = super().select(train_all)
        if force_rf:
            best = [r for r in sel if r["learner"] == "RF"][0]
        return sel, best


lt = LT(cfg)          # new: verifies the real lock (read-only); old: no lock check in __init__
d = pd.read_parquet(feat)
t = time.time()
R = lt.run(d)
print(f"{which} {feat.rsplit('/', 1)[-1]} force_rf={force_rf}: selected {R['selected']['set']}/{R['selected']['learner']} "
      f"in {time.time() - t:.0f}s", file=sys.stderr)
write_json(R, out)
