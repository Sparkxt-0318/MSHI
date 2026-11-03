"""Verifier's check of the claim in C-1 that the point estimates of all groups are the REML maxima: my own REML
(per-site dense blocks, Cholesky) evaluated at the committed estimates, then a bounded local polish (L-BFGS-B on the
variances, plus both faces) from there and from a few other starts; reports any llf gain."""
import sys
FZ = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
sys.path.insert(0, FZ)
import json
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

warnings.simplefilter("ignore")


class Blocks:
    def __init__(self, y, site, study):
        self.blocks = []
        cut = np.flatnonzero(np.r_[True, site[1:] != site[:-1], True])
        for a, b in zip(cut[:-1], cut[1:]):
            st = study[a:b]
            self.blocks.append((y[a:b], (st[:, None] == st[None, :]).astype(float)))
        self.N = len(y)

    def reml(self, t):
        s2a, s2b, s2e = t
        if s2e <= 0 or s2a < 0 or s2b < 0:
            return -np.inf
        ld = x11 = x1y = xyy = 0.0
        for yi, Bi in self.blocks:
            n = len(yi)
            V = s2e * np.eye(n) + s2a + s2b * Bi
            L = np.linalg.cholesky(V)
            z1 = np.linalg.solve(L, np.ones(n))
            zy = np.linalg.solve(L, yi)
            ld += 2 * np.log(np.diag(L)).sum()
            x11 += z1 @ z1
            x1y += z1 @ zy
            xyy += zy @ zy
        return -0.5 * ((self.N - 1) * np.log(2 * np.pi) + ld + np.log(x11) + xyy - x1y ** 2 / x11)


cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rr, sst, info = NC.prepare(pd.read_parquet(f"{FZ}/data/derived/records_analysis.parquet"),
                           pd.read_parquet(f"{FZ}/data/derived/sites_analysis_qc.parquet"), S)
groups = NC.build_groups(rr, sst, S.continents)
res = json.load(open(f"{FZ}/results/noise_ceiling.json"))
for name in ["Asia", "Europe", "North America", "South America", "Africa", "Oceania", "pooled"]:
    g = groups[name]
    y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), S.min_records)
    m = Blocks(y, site, study)
    comp = res["groups"][name]["components"]
    th0 = np.array([comp[k]["estimate"] for k in ("s2_site", "s2_study", "s2_record")])
    l0 = m.reml(th0)
    kept = res["groups"][name]["fit"]["kept"]
    sm_llf = res["groups"][name]["fit"]["candidates"][kept]["llf"]
    best = (l0, th0)
    tot = np.var(y)
    for t0 in (np.maximum(th0, [1e-6, 1e-6, 1e-6]), np.array([0.5, 0.25, 0.25]) * tot, np.array([0.2, 0.6, 0.2]) * tot):
        o = minimize(lambda t: -m.reml(t), t0, method="L-BFGS-B", bounds=[(0, None), (0, None), (1e-10, None)],
                     options={"ftol": 1e-15, "gtol": 1e-9, "maxiter": 500})
        if -o.fun > best[0]:
            best = (-o.fun, o.x)
    for free in (0, 1):
        def nll(x, free=free):
            t = np.zeros(3); t[free] = x[0]; t[2] = x[1]
            return -m.reml(t)
        o = minimize(nll, [0.5 * tot, 0.3 * tot], method="L-BFGS-B", bounds=[(0, None), (1e-10, None)],
                     options={"ftol": 1e-15, "gtol": 1e-9, "maxiter": 500})
        if -o.fun > best[0]:
            t = np.zeros(3); t[free] = o.x[0]; t[2] = o.x[1]
            best = (-o.fun, t)
    print(f"{name:14s} committed s2 {np.round(th0, 6).tolist()} (kept {kept}) llf statsmodels {sm_llf:.6f} mine "
          f"{l0:.6f} | best found {best[0]:.6f} s2 {np.round(best[1], 6).tolist()} | gain {best[0] - l0:.2e}", flush=True)
