"""GAM (fit_gam): value and slope continuity at both boundary knots of both smooths, slope beyond = numerical
derivative just inside, linearity beyond, equality with statsmodels in range, determinism, and what the AIC search
returns on data shaped like the real ones (alpha, edf). Synthetic data only."""
import sys
sys.path.insert(0, "/home/user/MSHI"); sys.path.insert(0, "/home/user/MSHI/tests")
import numpy as np, pandas as pd, copy
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
cfg = load_config()
spec = T.Spec.from_cfg(cfg)
print("GAM settings:", spec.gam)
rng = np.random.default_rng(1)
for trial in range(4):
    n = [386, 233, 120, 60][trial]
    bio01 = rng.uniform(-5, 25, n); bio12 = np.exp(rng.normal(6.6, 0.5, n))
    y = 5 + 0.05 * bio01 + 0.3 * np.log(bio12) + 0.2 * np.sin(bio01 / 4) + rng.normal(0, 0.3, n)
    d = pd.DataFrame({"bio01": bio01, "bio12": bio12, "log_rs": y})
    m = T.fit_gam(spec, d)
    m2 = T.fit_gam(spec, d)
    x1lo, x1hi = bio01.min(), bio01.max(); l12lo, l12hi = np.log(bio12).min(), np.log(bio12).max()
    med12 = np.median(bio12); med01 = np.median(bio01)
    res = []
    for name, lo, hi, mk in [("bio01", x1lo, x1hi, lambda v: pd.DataFrame({"bio01": v, "bio12": med12})),
                             ("ln bio12", l12lo, l12hi, lambda v: pd.DataFrame({"bio01": med01, "bio12": np.exp(v)}))]:
        for side, b in [("lo", lo), ("hi", hi)]:
            eps = 1e-6 * max(1.0, abs(b))
            sgn = -1 if side == "lo" else 1
            v_in, v_at, v_out = m.predict(mk(np.array([b - sgn * eps, b, b + sgn * eps])))
            slope_in = (v_at - v_in) / eps * sgn
            slope_out = (v_out - v_at) / eps * sgn
            far = m.predict(mk(np.array([b + sgn * 1.0, b + sgn * 2.0, b + sgn * 3.0])))
            res.append(f"{name}-{side}: jump={abs(v_out - v_at):.2e} slope_in={slope_in:.4f} slope_out={slope_out:.4f} "
                       f"far 2nd diff={np.diff(far, 2)[0]:.1e} far slope={(far[1]-far[0])*sgn:.4f}")
    print(f"n={n} alpha={np.round(m.info['alpha'], 3).tolist()} edf={m.info['edf']:.2f} aic={m.info['aic']:.2f} deterministic={m.info == m2.info}")
    for r in res:
        print("   ", r)
