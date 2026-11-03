"""Verifier's independent check of C-3 (analytic, not a simulation): for a new record drawn from the observed records'
studies at a site (study j with probability m_ij / n_i), the best predictor that is constant within the site, even
knowing the realised effects, is mu + a_i + sum_j w_ij b_ij (w_ij = m_ij / n_i). Its error is b_iJ - sum_j w_ij b_ij + e,
with E[error^2] = s2_study * (1 - w2_i) + s2_record, w2_i = sum_j w_ij^2. With one new record per site, R2 =
(s2_site + s2_study * mean_i w2_i) / total. Compared with the stage's same_study = (s2_site + s2_study) / total.
Means over all sites (singletons included, w2 = 1) and over the fitted sites (>= 2 records). Also a small Monte Carlo
of the same quantity written differently (draw the new record's study by its index), as a cross-check."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import json
import numpy as np
import pandas as pd
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

REPO = "/home/user/MSHI"
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
rng = np.random.default_rng(2026)
for name in ["Asia", "Europe", "North America", "South America", "Africa", "Oceania", "pooled"]:
    g = groups[name]
    c = res["groups"][name]["components"]
    a, b, e = (c[k]["estimate"] for k in ("s2_site", "s2_study", "s2_record"))
    tot = a + b + e
    same = res["groups"][name]["ceilings"]["same_study"]["estimate"]
    fit = g.n_rec >= 2
    r_all = (a + b * g.w2.mean()) / tot
    r_fit = (a + b * g.w2[fit].mean()) / tot
    # Monte Carlo: per site realise a, b_ij; pick a record uniformly among the site's records (so its study w.p. m/n)
    nsim, r2s = 2000, []
    for _ in range(nsim):
        ai = rng.normal(0, np.sqrt(a), len(g.site_ids))
        bvec = rng.normal(0, np.sqrt(b), int(g.n_study.sum()))
        off = np.cumsum(g.n_study) - g.n_study
        # study of every record (global index) and its site
        rec_study = np.concatenate([off[i] + g.study_local[g.start[i]:g.start[i] + g.n_rec[i]]
                                    for i in range(len(g.site_ids))]) if _ == 0 else rec_study
        rec_site = np.repeat(np.arange(len(g.site_ids)), g.n_rec) if _ == 0 else rec_site
        bw = np.bincount(rec_site, weights=bvec[rec_study], minlength=len(g.site_ids)) / g.n_rec   # sum_j w_j b_j
        pick = g.start + (rng.random(len(g.site_ids)) * g.n_rec).astype(int)                       # a random record
        ynew = ai + bvec[rec_study[pick]] + rng.normal(0, np.sqrt(e), len(g.site_ids))
        pred = ai + bw
        r2s.append(1 - np.mean((ynew - pred) ** 2) / tot)
    print(f"{name:14s} same_study (stage) {same:.4f} | best site-constant, analytic: all sites {r_all:.4f} "
          f"(gap {same - r_all:.4f}), fitted sites {r_fit:.4f} (gap {same - r_fit:.4f}) | MC (all sites, pop. variance) "
          f"{np.mean(r2s):.4f} | share of sites with >= 2 studies: all {np.mean(g.n_study >= 2):.3f}, fitted "
          f"{np.mean(g.n_study[fit] >= 2):.3f}")
