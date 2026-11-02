"""Monte-Carlo error of the CI bounds from boot_ci (copied from clean_test.py L68-77), on the exact Europe y (n=235)
with a synthetic prediction vector calibrated to the reported R2 (0.0790), bias (-0.046) and RMSE_rs (385.5)."""
import sys, json
import numpy as np, pandas as pd
from sklearn.metrics import r2_score
from scipy.optimize import minimize
W = sys.argv[1]
e = pd.read_parquet(f"{W}/out/europe_235.parquet"); y = e.log_rs.values; lon, lat = e.lon.values, e.lat.values
def boot_ci(y, p, lon=None, lat=None, deg=None, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    if deg is None:
        bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    else:
        b = (np.floor(lon / deg).astype(int).astype(str) + "_" + np.floor(lat / deg).astype(int).astype(str))
        u = np.unique(b); idx = {k: np.where(b == k)[0] for k in u}; bs = []
        for _ in range(n):
            i = np.concatenate([idx[k] for k in rng.choice(u, len(u))]); bs.append(r2_score(y[i], p[i]))
    return [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]
z = np.random.default_rng(1).standard_normal(len(y)); z = (z - z.mean()) / z.std()
yc = y - y.mean()
def mk(t): return y.mean() - 0.046 + t[0] * yc + t[1] * z
def loss(t):
    p = mk(t); return (r2_score(y, p) - 0.0790) ** 2 * 1e4 + ((np.sqrt(np.mean((np.exp(p) - np.exp(y)) ** 2)) - 385.5) / 385.5) ** 2 * 1e4
t = minimize(loss, [0.2, 0.15], method="Nelder-Mead").x; p = mk(t)
out = dict(beta=float(t[0]), gamma=float(t[1]), r2=float(r2_score(y, p)), rmse_rs=float(np.sqrt(np.mean((np.exp(p) - np.exp(y)) ** 2))),
           spearman=float(pd.Series(y).corr(pd.Series(p), method="spearman")),
           site_ci_seed42=boot_ci(y, p), block2_ci_seed42=boot_ci(y, p, lon, lat, 2.0))
lo_s = [boot_ci(y, p, seed=s)[0] for s in range(100)]
lo_b = [boot_ci(y, p, lon, lat, 2.0, seed=s)[0] for s in range(100)]
out["site_lower_bound_over_100_seeds"] = dict(sd=float(np.std(lo_s)), range=[float(min(lo_s)), float(max(lo_s))])
out["block2_lower_bound_over_100_seeds"] = dict(sd=float(np.std(lo_b)), range=[float(min(lo_b)), float(max(lo_b))])
out["block2_lower_bound_minus_point_mean"] = float(np.mean(lo_b) - out["r2"])
out["site_lower_bound_minus_point_mean"] = float(np.mean(lo_s) - out["r2"])
print(json.dumps(out, indent=1))
