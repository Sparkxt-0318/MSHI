"""Mechanism of the GAM error: eigenvalues of statsmodels' cov_der2 (the second-derivative penalty) for the two smooths
of a synthetic training set: the null-space eigenvalue (linear trend) is not 0 but roundoff; alpha times it becomes a
real penalty on the linear trend once alpha is large."""
import sys, warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from statsmodels.gam.api import BSplines
from mshi.config import load_config
from mshi.analysis import transfer as T
warnings.simplefilter("ignore")
cfg = load_config(); spec = T.Spec.from_cfg(cfg); g = spec.gam
d = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
tr = d[d.continent_geo == "Europe"]
X = T.design(tr, g["features"], g["log"])
bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
for name, sm in zip(["bio01", "ln bio12"], bs.smoothers):
    w = np.linalg.eigvalsh(sm.cov_der2)
    xv = sm.transform(sm.x)
    lin = np.linalg.lstsq(xv, sm.x - sm.x.min(), rcond=None)[0]          # coefficients of the linear trend
    pen = lin @ sm.cov_der2 @ lin
    print(f"{name}: eigenvalues of cov_der2 = {np.array2string(w, precision=3)}; penalty of the exact linear trend "
          f"c'Cc = {pen:.2e} (relative to max eigenvalue x |c|^2: {pen / (w.max() * (lin @ lin)):.1e})")
