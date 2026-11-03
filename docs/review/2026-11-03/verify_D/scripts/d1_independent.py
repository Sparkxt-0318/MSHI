"""Verifier's independent check of D-1 (phase2.transfer.xgb_from honoured by transfer_matrix only).

Different inputs from the reviewer's script: another synthetic draw (synth(seed=3)), an alternative block that
differs from clean_test.locked.xgb only in learning_rate, and a direct check of aoa.fit_xgb / the aoa result's
'xgb' record. Also: does us_r2 / aoa validate xgb_from at all (a dangling path)? Writes only under argv[1].
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
import numpy as np
import xgboost

from mshi.config import load_config
from mshi.analysis import aoa as A
from mshi.analysis import transfer as T
from mshi.analysis import us_r2 as U
import test_us_r2 as TU
from test_robustness import sandbox

cfg = load_config()
root = Path(sys.argv[1])
locked = copy.deepcopy(cfg["clean_test"]["locked"]["xgb"])
print("clean_test.locked.xgb:", locked)
print("committed phase2.transfer.xgb_from:", cfg["phase2"]["transfer"]["xgb_from"])


def edit_alt(d):
    TU.settings(d)
    alt = copy.deepcopy(d["clean_test"]["locked"]["xgb"])
    alt["learning_rate"] = alt["learning_rate"] / 2          # only the learning rate differs
    d["phase2"]["transfer"]["xgb_alt2"] = alt
    d["phase2"]["transfer"].update(learners=["OLS-TP", "XGB"], xgb_from="phase2.transfer.xgb_alt2")
    d["phase2"]["us_r2"]["xgb_seed_spread"] = [0, 0]


# ---- 1. transfer_matrix vs us_r2 on the shared row, other synthetic draw, other alternative block
sand = sandbox(cfg, Path(tempfile.mkdtemp(dir=root)), edit=edit_alt)
TU.record(sand, TU.synth(seed=3))
U.us_r2(sand)
T.transfer_matrix(sand)
R = json.loads(sand.path("results", "us_r2.json").read_text())
M = json.loads(sand.path("results", "transfer_matrix.json").read_text())
print("transfer_matrix XGB settings:", {k: M["learner_settings"]["XGB"][k] for k in ("learning_rate", "from")})
print("us_r2 XGB settings:          ", {k: R["learner_settings"]["XGB"][k] for k in ("learning_rate", "from")})
for learner in ("OLS-TP", "XGB"):
    t = next(r for r in M["main"] + M["supplementary"]
             if (r["table"], r["train"], r["test"], r["learner"]) == ("pairwise", "Asia", "North America", learner))
    u = next(r for r in R["rows"] if (r["variant"], r["target"], r["train"], r["test"], r["learner"]) ==
             ("qc", "site_mean", "Asia", "North America", learner))
    print(f"[seed-3 synth] {learner}: n_test {t['n_test']}/{u['n_test']}; r2 transfer_matrix {t['r2']:.6f} vs us_r2 "
          f"{u['r2']:.6f}; ci {['%.4f' % x for x in t['ci']['r2']]} vs {['%.4f' % x for x in u['ci']['r2']]}; "
          f"equal: {abs(t['r2'] - u['r2']) < 1e-12}")

# ---- 2. aoa.fit_xgb and the aoa result record ignore xgb_from
d = TU.synth(seed=3).features["qc"]
X = d[list(sand["phase2"]["c8"])].to_numpy("float32")
y = d.log_rs.to_numpy(float)
alt = sand["phase2"]["transfer"]["xgb_alt2"]
seed = sand["phase2"]["transfer"]["xgb_seed"]
p_aoa = A.fit_xgb(sand, X, y).predict(X)
p_alt = xgboost.XGBRegressor(**alt, random_state=seed).fit(X, y).predict(X)
p_lock = xgboost.XGBRegressor(**locked, random_state=seed).fit(X, y).predict(X)
print("aoa.fit_xgb == XGB(xgb_from block):", bool(np.array_equal(p_aoa, p_alt)),
      "| == XGB(clean_test.locked.xgb):", bool(np.array_equal(p_aoa, p_lock)),
      "| max |aoa - xgb_from block| =", float(np.max(np.abs(p_aoa - p_alt))))
print("transfer.fit_learner XGB == XGB(xgb_from block):",
      bool(np.array_equal(T.fit_learner(T.Spec.from_cfg(sand), "XGB", d).predict(d), p_alt.astype(float))))

# ---- 3. a dangling xgb_from: transfer refuses, us_r2 accepts silently
bad = sandbox(cfg, Path(tempfile.mkdtemp(dir=root)),
              edit=lambda dd: (TU.settings(dd), dd["phase2"]["transfer"].update(xgb_from="phase2.transfer.nope")))
try:
    T.Spec.from_cfg(bad)
    print("transfer Spec.from_cfg with dangling xgb_from: accepted")
except Exception as e:  # noqa: BLE001
    print(f"transfer Spec.from_cfg with dangling xgb_from: {type(e).__name__}: {e}")
S = U.Settings.from_cfg(bad)
print("us_r2 Settings.from_cfg with dangling xgb_from: accepted; describe()['XGB']['from'] =", S.describe()["XGB"]["from"])

# ---- 4. today (committed config): the three stages use the same block
c0 = load_config()
print("today: transfer Spec xgb == clean_test.locked.xgb:", T.Spec.from_cfg(c0).xgb == locked,
      "| us_r2 Settings xgb == locked:", U.Settings.from_cfg(c0).xgb == locked)
