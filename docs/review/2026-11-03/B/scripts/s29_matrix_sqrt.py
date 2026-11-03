"""Root cause of the GAM error: statsmodels' penalized_wls augments the design with matrix_sqrt(2 S_alpha), whose
singular-value threshold is ABSOLUTE (1e-15). For large alpha the roundoff singular values of the null space (the linear
trend, exactly 0 in theory) are ~1e-16 * alpha * lambda_max, far above 1e-15, so they are kept and penalise the linear
trend. Prints the null-space singular values of 2 S_alpha (synthetic Europe training set) for several alpha."""
import sys, warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from statsmodels.gam.api import BSplines
from statsmodels.gam.generalized_additive_model import GLMGam
from statsmodels.gam.gam_penalties import MultivariateGamPenalty
from mshi.config import load_config
from mshi.analysis import transfer as T
warnings.simplefilter("ignore")
cfg = load_config(); spec = T.Spec.from_cfg(cfg); g = spec.gam
d = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
tr = d[d.continent_geo == "Europe"]
X = T.design(tr, g["features"], g["log"])
bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
for la in (8, 12, 14, 15, 16):
    al = np.array([10.0 ** la] * 2)
    m = GLMGam(tr.log_rs.to_numpy(), exog=np.ones((len(X), 1)), smoother=bs, alpha=al)
    S = m.penal.penalty_matrix(alpha=al)            # what PIRLS uses (it augments with 2 * S)
    s = np.linalg.svd(2 * S, compute_uv=False)
    print(f"alpha=1e{la}: largest singular value {s[0]:.2e}; the 3 smallest (null space: constant + 2 linear trends) "
          f"{np.array2string(s[-3:], precision=2)}; kept by matrix_sqrt (> 1e-15): {int((s > 1e-15).sum())} of {len(s)}")
