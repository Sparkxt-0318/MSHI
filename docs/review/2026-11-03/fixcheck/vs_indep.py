"""Fallback fits vs the reviewer's independent REML maxima (South America, every bootstrap replicate)."""
import sys, json
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
from threadpoolctl import threadpool_limits
from mshi.config import load_config
from mshi.analysis import noise_ceiling as NC
own = {r["b"]: r for r in json.load(open(sys.argv[2]))["South America"]}
cfg = load_config(); s = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(cfg.path("derived", "records_analysis.parquet"))
sites = pd.read_parquet(cfg.path("derived", f"sites_analysis_{s.variant}.parquet"))
r, st, _ = NC.prepare(rec, sites, s); groups = NC.build_groups(r, st, s.continents)
g = groups["South America"]; gaps = []; worst = []
with threadpool_limits(limits=1):
    for b, d in enumerate(NC.draws(groups, s)):
        o = own.get(b)
        if o is None or o.get("own_llf") is None: continue
        f = NC.replicate_stats(g, d["South America"], s.min_records, s.optimizer)["fit"]
        if f["status"] != "ok":
            worst.append((b, "status " + f["status"])); continue
        llf = f["candidates"][f["chosen"]]["llf"]
        gap = o["own_llf"] - llf
        gaps.append(gap)
        comp = np.array([f["s2_site"], f["s2_study"], f["s2_record"]]); oc = np.array(o["own"])
        if gap > 1e-6 or np.abs(comp - oc).max() > 1e-3:
            worst.append((b, round(gap, 6), comp.round(4).tolist(), oc.round(4).tolist(), f["chosen"]))
gaps = np.array(gaps)
print("replicates compared", len(gaps), "max llf gap (own - kept)", gaps.max(), "min", gaps.min())
print("replicates with gap > 1e-6 or components off by > 1e-3:", worst)
