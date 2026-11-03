"""Seam: phase2.transfer.xgb_from names the XGBoost parameter block ("XGBoost with the original fixed parameters").
transfer.py reads it (Spec.from_cfg -> _lookup(cfg, tr["xgb_from"])); us_r2.py (and aoa.py) read
clean_test.locked.xgb directly. With xgb_from pointing at another block, do us_r2 and transfer_matrix still agree on
the Asia -> North America XGB row they share? Synthetic data from tests/test_us_r2.py (offline), sandboxed output.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.analysis import us_r2 as U
import test_us_r2 as TU
from test_robustness import sandbox

cfg = load_config()
tmp = Path(tempfile.mkdtemp(dir=sys.argv[1]))


def edit(d):
    TU.settings(d)
    alt = copy.deepcopy(d["clean_test"]["locked"]["xgb"])
    alt.update(max_depth=6, n_estimators=100)          # another parameter block
    d["phase2"]["transfer"]["xgb_alt"] = alt
    d["phase2"]["transfer"].update(learners=["OLS-TP", "XGB"], xgb_from="phase2.transfer.xgb_alt")
    d["phase2"]["us_r2"]["xgb_seed_spread"] = [0, 0]


sand = sandbox(cfg, tmp, edit=edit)
TU.record(sand, TU.synth())
U.us_r2(sand)
T.transfer_matrix(sand)
R = json.loads(sand.path("results", "us_r2.json").read_text())
M = json.loads(sand.path("results", "transfer_matrix.json").read_text())
print("transfer_matrix learner_settings XGB:", {k: M["learner_settings"]["XGB"][k] for k in ("max_depth", "n_estimators", "from")})
print("us_r2 learner_settings XGB:", {k: R["learner_settings"]["XGB"][k] for k in ("max_depth", "n_estimators", "from")})
for learner in ("OLS-TP", "XGB"):
    t = next(r for r in M["main"] + M["supplementary"]
             if (r["table"], r["train"], r["test"], r["learner"]) == ("pairwise", "Asia", "North America", learner))
    u = next(r for r in R["rows"] if (r["variant"], r["target"], r["train"], r["test"], r["learner"]) ==
             ("qc", "site_mean", "Asia", "North America", learner))
    print(f"{learner}: transfer_matrix r2 {t['r2']:.6f} rmse_log {t['rmse_log']:.6f} | us_r2 r2 {u['r2']:.6f} "
          f"rmse_log {u['rmse_log']:.6f} | equal: {abs(t['r2'] - u['r2']) < 1e-12}")
