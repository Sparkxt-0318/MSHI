"""statsmodels' REML log-likelihood of the no_study model (SA replicate b=2) at tiny cov_re/scale: is it ever spuriously
HIGH (which would make a fallback fit at a near-zero variance win the candidate choice)? Reference: the exact value at
cov_re = 0 is the intercept-only OLS REML, -85.3486."""
import sys
FZ = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
sys.path.insert(0, FZ)
import warnings
import numpy as np, pandas as pd
from statsmodels.regression.mixed_linear_model import MixedLM, MixedLMParams
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config
warnings.simplefilter("ignore")
cfg = load_config(); S = NC.Settings.from_cfg(cfg)
rr, sst, info = NC.prepare(pd.read_parquet(f"{FZ}/data/derived/records_analysis.parquet"),
                           pd.read_parquet(f"{FZ}/data/derived/sites_analysis_qc.parquet"), S)
groups = NC.build_groups(rr, sst, S.continents); D = NC.draws(groups, S)
g = groups["South America"]
y, site, study = NC.replicate(g, D[2]["South America"], S.min_records)
one = np.ones((len(y), 1))
m = MixedLM(y, one, groups=site, exog_re=one)
m.reml = True; m.cov_pen = None; m.fe_pen = None; m._cov_sing = 0; m._freepat = None
for rel in [1e-300, 1e-200, 1e-100, 1e-50, 1e-30, 1e-20, 1e-17, 1e-16, 1e-15, 1e-14, 1e-13, 1e-12, 1e-10, 1e-8, 1e-6, 1e-4]:
    p = MixedLMParams.from_components(fe_params=np.array([y.mean()]), cov_re=np.array([[rel]]))
    try:
        v = m.loglike(p, profile_fe=True)
    except Exception as e:
        v = f"{type(e).__name__}: {e}"
    print(f"cov_re/scale = {rel:8.0e}: statsmodels REML loglike {v}")
