"""C-1 check: South America bootstrap refits with lbfgs only vs [lbfgs, bfgs, nm] (the stage's draws, seed 7)."""
import sys, json, collections
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
from threadpoolctl import threadpool_limits
from mshi.config import load_config
from mshi.analysis import noise_ceiling as NC
cfg = load_config()
s = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(cfg.path("derived", "records_analysis.parquet"))
sites = pd.read_parquet(cfg.path("derived", f"sites_analysis_{s.variant}.parquet"))
r, st, _ = NC.prepare(rec, sites, s)
groups = NC.build_groups(r, st, s.continents)
g = groups["South America"]
reasons = collections.Counter(); below = []; failed_old = 0; failed_new = 0; fallback = collections.Counter()
with threadpool_limits(limits=1):
    for b, d in enumerate(NC.draws(groups, s)):
        old = NC.replicate_stats(g, d["South America"], s.min_records, ("lbfgs",))["fit"]
        new = NC.replicate_stats(g, d["South America"], s.min_records, s.optimizer)["fit"]
        bad_kinds = []
        for k, c in (old.get("candidates") or {}).items():
            if not c["usable"]:
                why = ("llf_inf" if c["llf"] is not None and not np.isfinite(c["llf"]) else
                       "error" if c["error"] else "not_converged")
                reasons[(k, why)] += 1
                bad_kinds.append(k)
        if old["status"] == "failed": failed_old += 1
        if new["status"] == "failed": failed_new += 1
        for k, c in (new.get("candidates") or {}).items():
            if c["usable"] and c["failed_methods"]: fallback[(k, c["method"])] += 1
        if old["status"] == "ok" and new["status"] == "ok":
            lo, ln = old["candidates"][old["chosen"]]["llf"], new["candidates"][new["chosen"]]["llf"]
            if ln - lo > 1e-6: below.append((b, round(ln - lo, 4)))
n_rep_bad = None
print(json.dumps({"unusable_lbfgs_candidates": {f"{k}:{w}": n for (k, w), n in sorted(reasons.items())},
                  "replicates_kept_fit_below_max": len(below), "of_which_gt_0.05": sum(x > 0.05 for _, x in below),
                  "max_gap": max([x for _, x in below], default=0), "below": below,
                  "failed_lbfgs_only": failed_old, "failed_with_fallback": failed_new,
                  "fallback_fits": {f"{k}:{m}": n for (k, m), n in sorted(fallback.items())}}, indent=1))
