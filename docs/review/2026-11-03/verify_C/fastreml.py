"""Closed-form REML log-likelihood of the nested model y = mu + a_site + b_study + e (intercept only), O(#studies) per
evaluation (compound-symmetric blocks: Sherman-Morrison and the matrix determinant lemma). Same value as the dense
common.reml_loglik (checked in c3c_fast.py)."""
import numpy as np
from scipy.optimize import minimize


def suffstats(y, site, study):
    """Per study: m, sum y, sum y^2, and its site index; site and study are integer codes (study nested in site)."""
    ns = int(study.max()) + 1
    m = np.bincount(study, minlength=ns).astype(float)
    s1 = np.bincount(study, weights=y, minlength=ns)
    s2 = np.bincount(study, weights=y * y, minlength=ns)
    st_site = np.zeros(ns, int)
    st_site[study] = site
    return m, s1, s2, st_site, int(site.max()) + 1, len(y)


def reml_fast(theta, ss):
    s2a, s2b, s2e = theta
    m, s1, s2, st_site, nsite, N = ss
    if s2e <= 0 or s2a < 0 or s2b < 0:
        return -np.inf
    d = s2e + m * s2b                                   # per study: 1'V_j^{-1}1 = m/d
    u = np.bincount(st_site, weights=m / d, minlength=nsite)
    t = np.bincount(st_site, weights=s1 / d, minlength=nsite)
    q = np.bincount(st_site, weights=(s2 - s2b * s1 * s1 / d) / s2e, minlength=nsite)
    ld = np.sum((m - 1) * np.log(s2e) + np.log(d)) + np.sum(np.log1p(s2a * u))
    xvx = np.sum(u / (1 + s2a * u))
    xvy = np.sum(t / (1 + s2a * u))
    yvy = np.sum(q - s2a * t * t / (1 + s2a * u))
    quad = yvy - xvy * xvy / xvx
    return -0.5 * ((N - 1) * np.log(2 * np.pi) + ld + np.log(xvx) + quad)


def reml_max(ss, extra_starts=(), y_var=None):
    """Bounded REML maximum over s2_site, s2_study >= 0, s2_record > 0 (L-BFGS-B from several starts, plus the two
    boundary faces and the corner by 1-D/2-D bounded searches)."""
    tot = y_var
    starts = [(0.5 * tot, 0.25 * tot, 0.25 * tot), (0.1 * tot, 0.6 * tot, 0.3 * tot), (0.8 * tot, 1e-6, 0.2 * tot),
              (1e-6, 0.8 * tot, 0.2 * tot), (1e-6, 1e-6, tot)] + [tuple(max(v, 1e-9) for v in s) for s in extra_starts]
    best = None
    for t0 in starts:
        o = minimize(lambda t: -reml_fast(t, ss), np.asarray(t0, float), method="L-BFGS-B",
                     bounds=[(0, None), (0, None), (1e-10, None)],
                     options={"maxiter": 2000, "ftol": 1e-15, "gtol": 1e-11})
        if best is None or o.fun < best.fun:
            best = o
    # boundary faces explicitly (2-parameter problems)
    for fix in (0, 1):
        free = [k for k in (0, 1) if k != fix]
        for t0 in starts:
            x0 = np.array([max(t0[free[0]], 1e-6), max(t0[2], 1e-6)])
            def nll(x, fix=fix, free=free):
                th = np.zeros(3)
                th[free[0]] = x[0]
                th[2] = x[1]
                return -reml_fast(th, ss)
            o = minimize(nll, x0, method="L-BFGS-B", bounds=[(0, None), (1e-10, None)],
                         options={"maxiter": 2000, "ftol": 1e-15, "gtol": 1e-11})
            if o.fun < best.fun:
                th = np.zeros(3)
                th[free[0]] = o.x[0]
                th[2] = o.x[1]
                best = type("R", (), {"fun": o.fun, "x": th})()
    return np.asarray(best.x, float), float(-best.fun)
