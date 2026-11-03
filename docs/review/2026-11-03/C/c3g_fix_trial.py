"""Check 3g: does a minimal fix restore the REML maxima? The stage's own bootstrap code for South America
(NC.replicate_stats on NC.draws) with _fit_candidate wrapped so that a candidate that raises, does not converge or
returns a non-finite llf is refitted with statsmodels' bfgs, then nm (fix A); and fix A plus a bounded polish of the
kept fit with the closed-form REML (fix B). CIs vs the stage and vs the REML maxima of c3d2."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import json, warnings
import numpy as np, pandas as pd
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits
from common import REPO
from fastreml import suffstats, reml_fast
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config
warnings.simplefilter("ignore")
cfg = load_config(); S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
orig = NC._fit_candidate
def retry(kind, y, site, study, optimizer):
    out = orig(kind, y, site, study, optimizer)
    for m in ("bfgs", "nm"):
        if out["usable"]:
            break
        out = orig(kind, y, site, study, m)
    return out
q = S.quantiles
g = groups["South America"]
res = {}
with threadpool_limits(limits=1):
    for label, fn, polish in (("fix A: retry", retry, False), ("fix A+B: retry + bounded polish", retry, True)):
        NC._fit_candidate = fn
        vals, st_counts = {"share_site": [], "ceiling_same_study": [], "ceiling_site_mean": []}, {}
        for d in D:
            draw = d["South America"]
            y, site, study = NC.replicate(g, draw, S.min_records)
            fit = NC.fit_nested(y, site, study, S.optimizer)
            st_counts[fit["status"]] = st_counts.get(fit["status"], 0) + 1
            if fit["status"] != "ok":
                continue
            th = np.array([fit["s2_site"], fit["s2_study"], fit["s2_record"]])
            if polish:
                ss = suffstats(y, site, study)
                o = minimize(lambda t: -reml_fast(t, ss), np.maximum(th, [0, 0, 1e-8]), method="L-BFGS-B",
                             bounds=[(0, None), (0, None), (1e-10, None)], options={"ftol": 1e-15, "gtol": 1e-11})
                if -o.fun > reml_fast(th, ss):
                    th = o.x
            c = NC.ceilings(*th, g.n_rec[draw], g.n_study[draw], g.w2[draw])
            for k in vals:
                vals[k].append(c[k])
        print(label, "status counts", st_counts)
        for k, v in vals.items():
            print(f"   {k:20s} CI {np.round(np.quantile(v, q), 4).tolist()} (n {len(v)})")
NC._fit_candidate = orig
