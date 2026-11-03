"""B-1 check (a): validate my exact reference and show statsmodels' error at large alpha, on stand-in data with real
site coordinates and SRDB-reported MAT/MAP (no outcome needed beyond a synthetic one here).
1. Reference vs statsmodels GLMGam at moderate alpha (statsmodels is accurate there): must agree to ~1e-9.
2. Reference vs the analytic limit OLS(1, MAT, ln MAP) as alpha -> inf (both alphas): must converge.
3. statsmodels vs the analytic limit at equal large alphas: no reference needed; any departure is numerical error.
4. Mixed alphas (one moderate, one large) vs reference."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/scripts")
import numpy as np
from statsmodels.gam.api import GLMGam
from vb1_common import standin_sites, basis, Exact, quiet
from mshi.config import load_config
from mshi.analysis import transfer as T

quiet()
cfg = load_config()
spec = T.Spec.from_cfg(cfg)
s = standin_sites()
print("stand-in sites by continent:", s.continent_geo.value_counts().to_dict())
rng = np.random.default_rng(11)
for cont in ("Asia", "North America", "South America"):
    tr = s[s.continent_geo == cont].copy()
    # synthetic outcome: mildly nonlinear in MAT, linear in ln MAP, noise 0.4 (only the covariates are real)
    tr["log_rs"] = 4.4 + 0.07 * tr.bio01 - 0.001 * tr.bio01 ** 2 + 0.3 * np.log(tr.bio12) + rng.normal(0, 0.4, len(tr))
    X, y, bs = basis(spec, tr)
    print(f"\n{cont}: n = {len(y)}; basis dims {[sm.dim_basis for sm in bs.smoothers]}; "
          f"MAT range {X[:,0].min():.1f}..{X[:,0].max():.1f}, ln MAP range {X[:,1].min():.2f}..{X[:,1].max():.2f}")
    Xl = np.c_[np.ones(len(y)), X]
    ols = Xl @ np.linalg.lstsq(Xl, y, rcond=None)[0]
    print(" log10 alpha | max|ref-sm|  max|ref-OLS|  max|sm-OLS|  edf ref  edf sm   aic ref   aic sm")
    for la in (-2, 0, 2, 4, 6, 8, 10, 12, 13, 14, 15, 16):
        al = np.full(2, 10.0 ** la)
        ref = Exact(X, y, bs, al)
        sm = GLMGam(y, exog=np.ones((len(y), 1)), smoother=bs, alpha=al).fit()
        print(f"   {la:4d}      | {np.max(np.abs(ref.fitted - sm.fittedvalues)):9.2e}  {np.max(np.abs(ref.fitted - ols)):9.2e}"
              f"  {np.max(np.abs(sm.fittedvalues - ols)):9.2e}  {ref.edf:6.3f}  {np.sum(sm.edf):6.3f}  {ref.aic:8.3f}  {sm.aic:8.3f}")
    print(" null-space residuals of the linear-function coefficients:", ["%.1e" % v for v in ref.null_resid])
    for amix in ([1e2, 1e14], [1e2, 1e15], [1e14, 1e2], [1e15, 1e2], [1e3, 1e16]):
        al = np.array(amix)
        ref = Exact(X, y, bs, al)
        sm = GLMGam(y, exog=np.ones((len(y), 1)), smoother=bs, alpha=al).fit()
        print(f"   mixed alpha {amix}: max|ref - sm| = {np.max(np.abs(ref.fitted - sm.fittedvalues)):.2e}; "
              f"edf ref {ref.edf:.3f} sm {np.sum(sm.edf):.3f}")
