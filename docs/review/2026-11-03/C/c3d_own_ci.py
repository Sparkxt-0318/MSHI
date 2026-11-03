"""Check 3d: the bootstrap CIs of every group recomputed with the bounded REML maximum of each replicate (closed-form
REML, no statsmodels), on the stage's own draws (NC.draws, seed 7, 200 replicates) and its identification rule, vs the
committed CIs in results/noise_ceiling.json."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import json
import numpy as np
import pandas as pd

from common import REPO
from fastreml import suffstats, reml_max
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

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
for name in list(S.continents) + [NC.POOLED]:
    g = groups[name]
    # point estimate
    y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), S.min_records)
    th0, _ = reml_max(suffstats(y, site, study), y_var=np.var(y))
    vals, n_ok = {k[2]: [] for k in KEYS}, 0
    for d in D:
        draw = d[name]
        y, site, study = NC.replicate(g, draw, S.min_records)
        idn = NC.identification(site, study)
        if idn["sites"] < 2 or idn["sites_2plus_studies"] < 1 or idn["studies_2plus_records"] < 1:
            continue
        th, _ = reml_max(suffstats(y, site, study), y_var=np.var(y))
        c = NC.ceilings(*th, g.n_rec[draw], g.n_study[draw], g.w2[draw])
        for k in KEYS:
            vals[k[2]].append(c[k[2]])
        n_ok += 1
    print(f"== {name}: identified replicates {n_ok}; point estimate (own REML max) s2 {np.round(th0, 5).tolist()}")
    out[name] = {}
    for sec, key, stat in KEYS:
        st = res["groups"][name][sec][key]
        ci = np.quantile(vals[stat], q).tolist()
        dlo, dhi = ci[0] - st["ci"][0], ci[1] - st["ci"][1]
        out[name][stat] = {"stage": st["ci"], "own": ci, "diff": [dlo, dhi]}
        flag = "  <-- differs by > 0.005" if max(abs(dlo), abs(dhi)) > 0.005 else ""
        print(f"  {stat:28s} stage {np.round(st['ci'], 4).tolist()} (n {st['n_boot_used']}) | REML maxima "
              f"{np.round(ci, 4).tolist()} (n {n_ok}) | diff [{dlo:+.4f}, {dhi:+.4f}]{flag}")
json.dump(out, open("c3d_own_ci.json", "w"), indent=1)
