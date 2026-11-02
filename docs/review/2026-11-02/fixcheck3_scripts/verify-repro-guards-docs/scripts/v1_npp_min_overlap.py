"""Claim 1: does the `both.sum() > 2` literal (repro_checks.py:134) change the NPP row status? Pure computation."""
import sys
import warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
from mshi.analysis.repro_checks import _row
from mshi.config import load_config
t = load_config()["reproduction_targets"]["npp_corr_original_sites"]
print("target", t)
for x, y in [([1.0, 2.0], [3.0, 5.0]), ([1.0, 2.0], [5.0, 3.0]), ([1.0], [2.0])]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = float(np.corrcoef(x, y)[0, 1])
    print(f"n={len(x)}: r without the literal = {r}; row status with r: {_row('NPP', t, r)['status']}; "
          f"row status with r=None (literal): {_row('NPP', t, None)['status']}")
