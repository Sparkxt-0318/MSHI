"""B-1 check (c): the worst cases of vb1b in detail.
1. A second, formulation-independent reference at extreme alpha: when one smooth's alpha is astronomically large its
   exact fit is linear, so the exact model equals a GAM with that smooth replaced by a linear column. Computed with a
   plain augmented least-squares (penalty root of the other smooth by Cholesky of C + tiny ridge only on the range,
   checked against my reference vb1_common.Exact).
2. Per-test-continent r2 of the synthetic South-America-trained GAM: fit_gam (current code), exact model at the AIC
   optimum, capped search (alpha <= 1e8).
3. The real-outcome LOCO training set (Europe held out; no European outcome used): capped vs exact search, the
   alphas and AICs; and the prediction differences on European covariates (no outcomes read)."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/scripts")
import warnings
import numpy as np
import pandas as pd
from statsmodels.gam.api import GLMGam
from vb1_common import standin_sites, basis, Exact, exact_aic_search, clipped_search
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.spatial import block_folds

warnings.simplefilter("ignore")
cfg = load_config()
spec = T.Spec.from_cfg(cfg)
g = spec.gam
s = standin_sites()
rng = np.random.default_rng(2026)
syn = s.copy()
syn["log_rs"] = (4.2 + 0.09 * syn.bio01 - 0.0018 * syn.bio01 ** 2 + 0.9 * np.log(syn.bio12)
                 - 0.05 * np.log(syn.bio12) ** 2 + rng.normal(0, 0.45, len(syn)))
conts = cfg["phase2"]["continents"]


def linear_limit(X, y, bs, j_lin, alpha_other):
    """Exact model when smooth j_lin's alpha -> inf: [1, x_jlin, B_other], penalty 2*alpha_other*C_other on B_other."""
    o = 1 - j_lin
    sm = bs.smoothers[o]
    w, U = np.linalg.eigh(sm.cov_der2)
    # penalty root on the range only: drop the single (numerically ~0) null eigenvalue
    keep = w > 1e-10 * w.max()
    R = (np.sqrt(2 * alpha_other * w[keep])[:, None] * U[:, keep].T)
    A = np.vstack([np.c_[np.ones(len(y)), X[:, j_lin], sm.basis], np.c_[np.zeros((R.shape[0], 2)), R]])
    b = np.r_[y, np.zeros(R.shape[0])]
    beta = np.linalg.lstsq(A, b, rcond=None)[0]
    return np.c_[np.ones(len(y)), X[:, j_lin], sm.basis] @ beta


# 1 + 2: synthetic South America transfer training set
tr = syn[syn.continent_geo == "South America"]
m = T.fit_gam(spec, tr)
X, y, bs = basis(spec, tr)
a = np.array(m.info["alpha"])
ex = Exact(X, y, bs, a)
ll = linear_limit(X, y, bs, int(np.argmax(a)), a[1 - int(np.argmax(a))])
print(f"SA synthetic: fit_gam alpha {a}, edf {m.info['edf']:.3f}; exact edf {ex.edf:.3f}")
print(f"  second reference (linear column) vs my reference: max diff {np.max(np.abs(ll - ex.fitted)):.2e}; "
      f"fit_gam vs second reference: {np.max(np.abs(m.predict(tr) - ll)):.3f}")
sm_lin = np.c_[np.ones(len(y)), X]
print(f"  fitted slopes on MAT (OLS of fitted values on [1, MAT, ln MAP]): fit_gam "
      f"{np.linalg.lstsq(sm_lin, m.predict(tr), rcond=None)[0][1]:.4f}, exact {np.linalg.lstsq(sm_lin, ex.fitted, rcond=None)[0][1]:.4f}")
a_ex = exact_aic_search(X, y, bs)
ex_opt = Exact(X, y, bs, a_ex)
a_cap, res_cap = clipped_search(y, bs, np.log(1e8))
print(f"  exact AIC search alpha {a_ex} (AIC {ex_opt.aic:.3f}); capped search alpha {a_cap} (statsmodels AIC {res_cap.aic:.3f}, "
      f"exact AIC at that alpha {Exact(X, y, bs, a_cap).aic:.3f})")
for c in conts:
    if c == "South America":
        continue
    te = syn[syn.continent_geo == c]
    yt = te.log_rs.to_numpy()
    Xt = T.design(te, g["features"], g["log"])
    Bt = np.hstack([T.spline_basis(sm, Xt[:, j]) for j, sm in enumerate(bs.smoothers)])
    p_cur, p_ex, p_cap = m.predict(te), ex_opt.predict_x(Xt), res_cap.params[0] + Bt @ np.asarray(res_cap.params)[1:]
    print(f"  SA -> {c:14s} n={len(te):4d} r2 fit_gam {T.r2(yt, p_cur):8.3f} | exact AIC-opt {T.r2(yt, p_ex):8.3f} | "
          f"capped {T.r2(yt, p_cap):8.3f} | max|pred diff| {np.max(np.abs(p_cur - p_ex)):.3f}")

# 3: real outcomes, LOCO training set for held-out Europe (Asia, NA, SA, Africa, Oceania); Europe covariates only
tr = s[s.continent_geo.isin([c for c in conts if c != "Europe"])]
m = T.fit_gam(spec, tr)
X, y, bs = basis(spec, tr)
a = np.array(m.info["alpha"])
a_ex = exact_aic_search(X, y, bs)
ex_opt, ex_same = Exact(X, y, bs, a_ex), Exact(X, y, bs, a)
a_cap, res_cap = clipped_search(y, bs, np.log(1e8))
ex_cap = Exact(X, y, bs, a_cap)
print(f"\nreal LOCO (Europe held out) n={len(y)}: fit_gam alpha {a} statsmodels AIC {m.info['aic']:.3f} (exact AIC at that alpha "
      f"{ex_same.aic:.3f}); exact search alpha {a_ex} AIC {ex_opt.aic:.3f}; capped alpha {a_cap} statsmodels AIC "
      f"{res_cap.aic:.3f}, exact AIC {ex_cap.aic:.3f}; capped vs exact at capped alpha {np.max(np.abs(res_cap.fittedvalues - ex_cap.fitted)):.1e}")
te = s[s.continent_geo == "Europe"]
Xt = T.design(te, g["features"], g["log"])          # covariates only; Europe's outcomes are not read
Bt = np.hstack([T.spline_basis(sm, Xt[:, j]) for j, sm in enumerate(bs.smoothers)])
p_cur, p_ex = m.predict(te), ex_opt.predict_x(Xt)
p_cap = res_cap.params[0] + Bt @ np.asarray(res_cap.params)[1:]
print(f"  predictions at the {len(te)} European sites: max|fit_gam - exact AIC-opt| {np.max(np.abs(p_cur - p_ex)):.3f}, "
      f"mean {np.mean(p_cur - p_ex):+.4f}; max|capped - exact AIC-opt| {np.max(np.abs(p_cap - p_ex)):.3f}")
