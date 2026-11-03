"""Check 3d (single-threaded, fewer starts): bootstrap CIs recomputed with the bounded REML maximum of each replicate
(closed-form REML, no statsmodels) on the stage's own draws, vs the committed CIs. Usage: c3d2_own_ci.py <group>..."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C")
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits
from common import REPO
from fastreml import suffstats, reml_fast
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config


def rmax(ss, tot):
    best = (np.inf, None)
    for t0 in [(0.5 * tot, 0.25 * tot, 0.25 * tot), (0.8 * tot, 1e-6, 0.2 * tot), (1e-6, 0.8 * tot, 0.2 * tot)]:
        o = minimize(lambda t: -reml_fast(t, ss), np.asarray(t0), method="L-BFGS-B",
                     bounds=[(0, None), (0, None), (1e-10, None)], options={"maxiter": 3000, "ftol": 1e-15, "gtol": 1e-11})
        if o.fun < best[0]:
            best = (o.fun, o.x)
    for free in (0, 1):                                  # the two boundary faces
        def nll(x, free=free):
            th = np.zeros(3); th[free] = x[0]; th[2] = x[1]
            return -reml_fast(th, ss)
        o = minimize(nll, np.array([0.7 * tot, 0.3 * tot]), method="L-BFGS-B", bounds=[(0, None), (1e-10, None)],
                     options={"maxiter": 3000, "ftol": 1e-15, "gtol": 1e-11})
        if o.fun < best[0]:
            th = np.zeros(3); th[free] = o.x[0]; th[2] = o.x[1]
            best = (o.fun, th)
    return np.asarray(best[1], float), -best[0]


cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
q = S.quantiles
KEYS = [("shares", "site", "share_site"), ("shares", "study", "share_study"),
        ("ceilings", "independent_study", "ceiling_independent_study"),
        ("ceilings", "same_study", "ceiling_same_study"), ("ceilings", "site_mean", "ceiling_site_mean")]
out = {}
with threadpool_limits(limits=1):
    for name in sys.argv[1:]:
        g = groups[name]
        y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), S.min_records)
        th0, l0 = rmax(suffstats(y, site, study), np.var(y))
        st0 = res["groups"][name]["components"]
        print(f"== {name}: point own REML max s2 {np.round(th0, 6).tolist()} llf {l0:.6f} | stage "
              f"{[round(st0[k]['estimate'], 6) for k in ('s2_site', 's2_study', 's2_record')]}", flush=True)
        vals, n_ok = {k[2]: [] for k in KEYS}, 0
        for d in D:
            draw = d[name]
            y, site, study = NC.replicate(g, draw, S.min_records)
            idn = NC.identification(site, study)
            if idn["sites"] < 2 or idn["sites_2plus_studies"] < 1 or idn["studies_2plus_records"] < 1:
                continue
            th, _ = rmax(suffstats(y, site, study), np.var(y))
            c = NC.ceilings(*th, g.n_rec[draw], g.n_study[draw], g.w2[draw])
            for k in KEYS:
                vals[k[2]].append(c[k[2]])
            n_ok += 1
        out[name] = {}
        for sec, key, stat in KEYS:
            st = res["groups"][name][sec][key]
            ci = np.quantile(vals[stat], q).tolist()
            dlo, dhi = ci[0] - st["ci"][0], ci[1] - st["ci"][1]
            out[name][stat] = {"stage": st["ci"], "own": ci, "diff": [dlo, dhi]}
            flag = "  <-- differs by > 0.005" if max(abs(dlo), abs(dhi)) > 0.005 else ""
            print(f"  {stat:28s} stage {np.round(st['ci'], 4).tolist()} (n {st['n_boot_used']}) | REML maxima "
                  f"{np.round(ci, 4).tolist()} (n {n_ok}) | diff [{dlo:+.4f}, {dhi:+.4f}]{flag}", flush=True)
json.dump(out, open("c3d2_own_ci_" + "_".join(a.replace(" ", "") for a in sys.argv[1:]) + ".json", "w"), indent=1)
