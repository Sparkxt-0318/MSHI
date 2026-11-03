"""Check 1: recompute the REML variance components independently (statsmodels formula interface as N3, and an own
REML maximised over the closed parameter space with L-BFGS-B bounds), compare with results/noise_ceiling.json."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import json
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
import statsmodels.formula.api as smf

from common import REPO, CONTINENTS, load_real, reml_loglik, codes

warnings.simplefilter("ignore")
res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
r, s = load_real()
r = r.sort_values(["site", "study", "rec_id"], kind="mergesort")

def own_reml(y, site, study, starts):
    best = None
    def nll(t):
        return -reml_loglik(t, y, site, study)[0]
    for t0 in starts:
        o = minimize(nll, t0, method="L-BFGS-B", bounds=[(0, None), (0, None), (1e-8, None)],
                     options={"maxiter": 500, "ftol": 1e-14, "gtol": 1e-10})
        if best is None or o.fun < best.fun:
            best = o
    return best

out = {}
for name in ["Asia", "Europe", "South America", "Africa", "Oceania", "North America", "pooled"]:
    d = r if name == "pooled" else r[r.cont == name]
    multi = d[d.groupby("site").log_rs.transform("size") >= 2].copy()
    y, site, study = codes(multi)
    # N3 formula model
    n3 = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1",
                     vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
    n3c = (float(np.asarray(n3.cov_re)[0, 0]), float(n3.vcomp[0]), float(n3.scale))
    # own REML log-lik at the N3 estimate (should equal n3.llf: profiled = full REML at the optimal scale)
    ll_n3_own = reml_loglik(n3c, y, site, study)[0]
    g = res["groups"][name]
    st = (g["components"]["s2_site"]["estimate"], g["components"]["s2_study"]["estimate"],
          g["components"]["s2_record"]["estimate"])
    ll_stage_own = reml_loglik(st, y, site, study)[0]
    cand = {k: (v["s2_site"], v["s2_study"], v["s2_record"], v["llf"]) for k, v in g["fit"]["candidates"].items()}
    cand_own = {k: reml_loglik(v[:3], y, site, study)[0] for k, v in cand.items()}
    tot = np.var(y)
    starts = [(0.5 * tot, 0.25 * tot, 0.25 * tot), (0.1 * tot, 0.6 * tot, 0.3 * tot), (0.8 * tot, 1e-3, 0.2 * tot),
              (1e-3, 0.8 * tot, 0.2 * tot), st]
    o = own_reml(y, site, study, starts)
    out[name] = {"n_records_fit": int(len(y)), "n_sites_fit": int(site.max() + 1),
                 "n3_formula": {"s2": n3c, "llf": float(n3.llf), "own_llf_at_n3": float(ll_n3_own),
                                "converged": bool(n3.converged)},
                 "stage": {"s2": st, "kept": g["fit"]["kept"], "own_llf_at_stage": float(ll_stage_own)},
                 "candidates_stage_llf_vs_own": {k: (cand[k][3], float(cand_own[k])) for k in cand},
                 "own_bounded_reml": {"s2": [float(v) for v in o.x], "llf": float(-o.fun)}}
    print(f"== {name}: records_fit {len(y)} sites_fit {site.max()+1}")
    print(f"  N3 formula : s2 {np.round(n3c, 6)} llf {n3.llf:.6f} (own llf at it {ll_n3_own:.6f}) conv {n3.converged}")
    print(f"  stage kept : {g['fit']['kept']} s2 {np.round(st, 6)} own llf at it {ll_stage_own:.6f}")
    for k in cand:
        print(f"    cand {k:9s}: stage llf {cand[k][3]:.6f}  own llf {cand_own[k]:.6f}  diff {cand[k][3]-cand_own[k]:+.2e}")
    print(f"  own bounded REML: s2 {np.round(o.x, 6)} llf {-o.fun:.6f}  (stage kept - own max: {ll_stage_own + o.fun:+.2e})")
json.dump(out, open("c1_reml.json", "w"), indent=1, default=float)
