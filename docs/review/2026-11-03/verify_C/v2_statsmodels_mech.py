"""Verifier's check of the mechanism in C-1 on South America replicate b=2 (the stage's own draw):
(1) why statsmodels reports llf = +inf for the no_study fit (cov_re exactly 0 -> log det of cov_re = -inf);
(2) whether the config's existing list form of the optimizer (statsmodels tries methods in turn until one converges)
    would avoid it: method=['lbfgs', 'bfgs'];
(3) what the stage keeps (fit_nested with optimizer 'lbfgs', and with the list ('lbfgs', 'bfgs'));
(4) the REML log-likelihood of the no_study model at cov_re -> 0 computed directly (finite), i.e. +inf is an artefact."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen")
import warnings
import numpy as np
import pandas as pd
from statsmodels.regression.mixed_linear_model import MixedLM
from threadpoolctl import threadpool_limits
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

warnings.simplefilter("ignore")
REPO = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
g = groups["South America"]
with threadpool_limits(limits=1):
    y, site, study = NC.replicate(g, D[2]["South America"], S.min_records)
    one = np.ones((len(y), 1))
    m = MixedLM(y, one, groups=site, exog_re=one)
    f = m.fit(reml=True, method="lbfgs")
    print("no_study lbfgs: converged", f.converged, "llf", f.llf, "cov_re", np.asarray(f.cov_re).ravel(), "scale", f.scale)
    print("  params_object.cov_re", f.params_object.cov_re.ravel(), " slogdet", np.linalg.slogdet(f.params_object.cov_re))
    print("  optimiser history (last):", {k: v for k, v in (f.hist[-1] if f.hist else {}).items() if k != "params"}
          if isinstance(getattr(f, "hist", None), list) else None)
    # tiny positive cov_re: the REML log-likelihood of the same model there (finite)
    from statsmodels.regression.mixed_linear_model import MixedLMParams
    m2 = MixedLM(y, one, groups=site, exog_re=one)
    m2.reml = True
    m2.cov_pen = None
    m2.fe_pen = None
    m2._cov_sing = 0
    m2._freepat = None
    for rel in (1e-12, 1e-6, 0.7325):
        p = MixedLMParams.from_components(fe_params=np.array([y.mean()]), cov_re=np.array([[rel]]))
        try:
            print(f"  loglike(profile_fe=True) at cov_re/scale = {rel:g}: {m2.loglike(p, profile_fe=True):.6f}")
        except Exception as e:  # noqa: BLE001
            print(f"  loglike at {rel}: {type(e).__name__}: {e}")
    # REML of the intercept-only OLS model (cov_re = 0 exactly), by hand
    N = len(y)
    s2 = np.var(y, ddof=1)
    ll0 = -0.5 * ((N - 1) * np.log(2 * np.pi * s2) + (N - 1) + np.log(N))
    print(f"  REML log-likelihood at cov_re = 0 by hand (OLS, intercept only): {ll0:.6f}")
    for meth in (["lbfgs", "bfgs"], ["lbfgs", "nm"]):
        f2 = MixedLM(y, one, groups=site, exog_re=one).fit(reml=True, method=meth)
        print(f"no_study method={meth}: converged {f2.converged} llf {f2.llf} cov_re {np.asarray(f2.cov_re).ravel()}")
    for opt in ("lbfgs", ("lbfgs", "bfgs")):
        fit = NC.fit_nested(y, site, study, opt)
        print(f"fit_nested optimizer={opt}: chosen {fit['chosen']} s2 ({fit['s2_site']:.6f}, {fit['s2_study']:.6f}, "
              f"{fit['s2_record']:.6f}); candidate llfs " + ", ".join(f"{k} {v['llf']}" for k, v in fit['candidates'].items()))
