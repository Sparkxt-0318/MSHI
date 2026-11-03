"""Verifier's check of the fix for C-1, per replicate (not only the CI quantiles): the stage's fit_nested with
_fit_candidate patched so that a candidate that raises, does not converge, or returns a non-finite llf or variance is
refitted with the next method of (lbfgs, bfgs, nm) [fix A]; and fix A plus a bounded polish of the kept fit on the
variance scale with my dense REML [fix A+B]. Every replicate's kept fit is compared with my independent REML maximum
(v1_indep_reml_<group>.json). Usage: v4_fix_check.py <group>"""
import sys
FZ = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
OUT = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C"
sys.path.insert(0, FZ)
sys.path.insert(0, OUT)
import json
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config
from v1f_indep_reml import Prof

warnings.simplefilter("ignore")
name = sys.argv[1]
mine = {r["b"]: r for r in json.load(open(f"{OUT}/v1_indep_reml_{name.replace(' ', '')}.json"))}
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{FZ}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{FZ}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
res = json.load(open(f"{FZ}/results/noise_ceiling.json"))
g = groups[name]
q = S.quantiles
orig = NC._fit_candidate
n_retry = {"n": 0}


def retry(kind, y, site, study, optimizer):
    out = orig(kind, y, site, study, optimizer)
    for m in ("bfgs", "nm"):
        if out["usable"]:
            break
        n_retry["n"] += 1
        out = orig(kind, y, site, study, m)
    return out


NC._fit_candidate = retry
stats = {"A": {"vals": {}, "gaps": [], "status": {}}, "A+B": {"vals": {}, "gaps": [], "status": {}}}
KEYS = ("share_site", "share_study", "ceiling_same_study", "ceiling_site_mean")
with threadpool_limits(limits=1):
    for b, d in enumerate(D):
        draw = d[name]
        y, site, study = NC.replicate(g, draw, S.min_records)
        fit = NC.fit_nested(y, site, study, S.optimizer)
        for lab in ("A", "A+B"):
            stats[lab]["status"][fit["status"]] = stats[lab]["status"].get(fit["status"], 0) + 1
        if fit["status"] != "ok":
            continue
        p = Prof(y, site, study)
        th = np.array([fit["s2_site"], fit["s2_study"], fit["s2_record"]])
        llA = p.full(*th)
        o = minimize(lambda t: -p.full(*t) if t[2] > 0 else np.inf, np.maximum(th, [0, 0, 1e-8]), method="L-BFGS-B",
                     bounds=[(0, None), (0, None), (1e-10, None)], options={"ftol": 1e-15, "gtol": 1e-10})
        thB, llB = (o.x, -o.fun) if -o.fun > llA else (th, llA)
        for lab, t, ll in (("A", th, llA), ("A+B", thB, llB)):
            stats[lab]["gaps"].append((b, mine[b]["mine"]["llf"] - ll))
            c = NC.ceilings(*t, g.n_rec[draw], g.n_study[draw], g.w2[draw])
            for k in KEYS:
                stats[lab]["vals"].setdefault(k, []).append(c[k])
NC._fit_candidate = orig
print(f"== {name}: candidate refits with a fallback method: {n_retry['n']}")
stage = res["groups"][name]
for lab, s_ in stats.items():
    gaps = np.array([x[1] for x in s_["gaps"]])
    big = [(b, round(gp, 4)) for b, gp in s_["gaps"] if gp > 1e-3]
    print(f" fix {lab}: status {s_['status']}; replicates whose kept fit is below my REML max by > 1e-3: {len(big)} "
          f"{big}; max gap {gaps.max():.2e}")
    for k in KEYS:
        st = stage["shares"][k.removeprefix("share_")] if k.startswith("share_") else stage["ceilings"][k.removeprefix("ceiling_")]
        print(f"   {k:20s} CI {np.round(np.quantile(s_['vals'][k], q), 4).tolist()} (n {len(s_['vals'][k])}) | "
              f"committed {np.round(st['ci'], 4).tolist()} (n {st['n_boot_used']})")
