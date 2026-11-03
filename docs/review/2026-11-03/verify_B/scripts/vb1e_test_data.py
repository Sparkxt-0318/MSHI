"""B-1: the data of tests/test_transfer.py::test_gam_equals_statsmodels_in_range_and_is_linear_beyond (synth_sites,
first 150 rows; log Rs exactly linear in MAT and ln MAP plus noise): the alpha fit_gam selects there, and the distance
of its fit from the exact model (vb1_common.Exact) at that alpha -- the test compares with statsmodels at the same alpha,
so it passes either way."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/scripts")
sys.path.insert(0, "/home/user/MSHI/tests")
import warnings
import numpy as np
from vb1_common import basis, Exact
from mshi.config import load_config
from mshi.analysis import transfer as T
from test_transfer import synth_sites
warnings.simplefilter("ignore")
spec = T.Spec.from_cfg(load_config())
d = synth_sites().iloc[:150].reset_index(drop=True)
m = T.fit_gam(spec, d)
X, y, bs = basis(spec, d)
ex = Exact(X, y, bs, np.array(m.info["alpha"]))
print(f"test data: fit_gam alpha {m.info['alpha']}, edf {m.info['edf']:.3f} (exact edf {ex.edf:.3f}); "
      f"max|fit_gam - exact| = {np.max(np.abs(m.predict(d) - ex.fitted)):.2e}")
