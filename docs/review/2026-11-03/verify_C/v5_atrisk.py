"""Verifier's check whether C-1 reaches a large group: run the stage's fit_nested (unchanged) on every bootstrap replicate
of <group>, list the replicates where a candidate was unusable (raised, did not converge, llf non-finite), and for
those (only) compute my independent REML maximum (dense scale-profiled REML, coarse grid + local refinement) and compare
with the kept fit. Usage: v5_atrisk.py <group>"""
import sys
FZ = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
OUT = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C"
sys.path.insert(0, FZ)
sys.path.insert(0, OUT)
import json
import time
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from threadpoolctl import threadpool_limits
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config
from v1f_indep_reml import Prof

warnings.simplefilter("ignore")


def reml_max_coarse(p: Prof):
    grid = np.r_[0.0, np.geomspace(1e-3, 1e2, 25)]
    GA, GB = np.meshgrid(grid, grid, indexing="ij")
    ga, gb = GA.ravel(), GB.ravel()
    ll = np.empty(len(ga))
    for a in range(0, len(ga), 16):
        ll[a:a + 16] = p.batch(ga[a:a + 16], gb[a:a + 16])[0]
    cands = [(ll.max(), ga[ll.argmax()], gb[ll.argmax()])]
    for face in ("all", "ga0", "gb0"):
        m = {"all": np.ones_like(ga, bool), "ga0": ga == 0, "gb0": gb == 0}[face]
        kk = int(np.flatnonzero(m)[np.argmax(ll[m])])
        o = minimize(lambda x: -p.one(x[0], x[1])[0], [ga[kk], gb[kk]], method="L-BFGS-B",
                     bounds=[(0, None), (0, None)], options={"ftol": 1e-15, "gtol": 1e-10, "maxiter": 500})
        cands.append((-o.fun, o.x[0], o.x[1]))
    for face in ("ga0", "gb0"):
        f = (lambda t: -p.one(0.0, t)[0]) if face == "ga0" else (lambda t: -p.one(t, 0.0)[0])
        o2 = minimize_scalar(lambda u: f(np.exp(u)), bounds=(np.log(1e-8), np.log(1e3)), method="bounded",
                             options={"xatol": 1e-10})
        cands.append((-o2.fun, 0.0, np.exp(o2.x)) if face == "ga0" else (-o2.fun, np.exp(o2.x), 0.0))
    llb, a, b = max(cands, key=lambda c: c[0])
    s2 = p.one(a, b)[1]
    return float(llb), [a * s2, b * s2, s2]


name = sys.argv[1]
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{FZ}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{FZ}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
g = groups[name]
t0 = time.time()
atrisk, status = [], {}
with threadpool_limits(limits=1):
    for b, d in enumerate(D):
        y, site, study = NC.replicate(g, d[name], S.min_records)
        fit = NC.fit_nested(y, site, study, S.optimizer)
        status[fit["status"]] = status.get(fit["status"], 0) + 1
        c = fit.get("candidates") or {}
        bad = {k: ("raised" if v["error"] else "llf_inf" if v["llf"] is not None and not np.isfinite(v["llf"])
                   else "not_converged" if not v["converged"] else "other") for k, v in c.items() if not v["usable"]}
        if bad:
            atrisk.append((b, fit, bad, (y, site, study)))
    print(f"== {name}: stage fits of {len(D)} replicates in {time.time() - t0:.0f} s; status {status}; replicates with an "
          f"unusable candidate: {len(atrisk)} {[(b, bad) for b, _f, bad, _ in atrisk]}", flush=True)
    for b, fit, bad, (y, site, study) in atrisk:
        p = Prof(y, site, study)
        llm, s2m = reml_max_coarse(p)
        if fit["status"] == "ok":
            kept = [fit["s2_site"], fit["s2_study"], fit["s2_record"]]
            llk = p.full(*kept)
            print(f"  b={b}: kept {fit['chosen']} s2 {np.round(kept, 5).tolist()} llf {llk:.5f} | my max s2 "
                  f"{np.round(s2m, 5).tolist()} llf {llm:.5f} | gap {llm - llk:.2e}", flush=True)
        else:
            print(f"  b={b}: status {fit['status']} | my max s2 {np.round(s2m, 5).tolist()} llf {llm:.5f}", flush=True)
print(f"done in {time.time() - t0:.0f} s")
