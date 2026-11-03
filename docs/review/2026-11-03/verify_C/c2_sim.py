"""Check 2: simulate from the fitted components with the real design (sites, studies, record counts) and compute the
empirical R2 of a perfect site-level predictor against (a) one new record from a new study, (b) a new record from an
observed study, (c) the record-weighted site mean; compare with the three ceilings of results/noise_ceiling.json.
Also: the expectation of the two variance checks under the model, and the stage's design arrays (n_rec, n_study, w2)
against an independent derivation."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C")
import json
import numpy as np
import pandas as pd

from common import REPO, CONTINENTS, load_real
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
r, s = load_real()

# the stage's own groups (read the same tables; nothing written)
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)

rng = np.random.default_rng(12345)
NSIM = 500
out = {}
for name in ["Asia", "Europe", "North America", "South America", "pooled"]:
    g = groups[name]
    # independent design from the records
    d = r if name == "pooled" else r[r.cont == name]
    m = d.groupby(["site", "study"]).size()
    n_i = m.groupby(level=0).sum()
    J_i = m.groupby(level=0).size()
    w2_i = ((m / m.groupby(level=0).transform("sum")) ** 2).groupby(level=0).sum()
    ids = list(g.site_ids)
    assert np.array_equal(n_i.reindex(ids).to_numpy(), g.n_rec), name
    assert np.array_equal(J_i.reindex(ids).to_numpy(), g.n_study), name
    assert np.allclose(w2_i.reindex(ids).to_numpy(), g.w2, rtol=0, atol=1e-15), name

    c = res["groups"][name]["components"]
    s2a, s2b, s2e = (c[k]["estimate"] for k in ("s2_site", "s2_study", "s2_record"))
    tot = s2a + s2b + s2e
    # design: per site, the list of study sizes
    sizes = [m.loc[sid].to_numpy() for sid in ids]
    S_ = len(ids)
    J = np.array([len(x) for x in sizes])
    flat_m = np.concatenate(sizes)                       # records per study, studies in site order
    study_site = np.repeat(np.arange(S_), J)
    n = g.n_rec.astype(float)
    R2 = {"a_new_study": [], "b_obs_study_pred_site": [], "b_obs_study_pred_site_and_study": [],
          "b_obs_study_pred_site_with_known_b": [], "c_site_mean": []}
    chk_mean, chk_single = [], []
    single = g.n_rec == 1
    for _ in range(NSIM):
        a = rng.normal(0, np.sqrt(s2a), S_)
        b = rng.normal(0, np.sqrt(s2b), len(flat_m))
        # sum over a study's records of e: N(0, m s2e); site mean = a + sum_j m_j b_j / n + sum e / n
        esum = rng.normal(0, np.sqrt(flat_m * s2e))
        bw = np.bincount(study_site, weights=flat_m * b, minlength=S_)
        ew = np.bincount(study_site, weights=esum, minlength=S_)
        ybar = a + (bw + ew) / n
        pred = a                                           # perfect site-level predictor (mu = 0)
        def r2(y, p):
            return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)
        # (a) one new record from a new study at every site
        ya = a + rng.normal(0, np.sqrt(s2b), S_) + rng.normal(0, np.sqrt(s2e), S_)
        R2["a_new_study"].append(r2(ya, pred))
        # (b) one new record from an observed study (study drawn with probability m_ij / n_i, i.e. as a random record)
        u = rng.random(S_)
        cum = np.cumsum(flat_m) - np.repeat(np.cumsum(n) - n, J)          # cumulative within-site sizes
        # pick study: first study whose within-site cumulative size exceeds u * n
        thr = np.repeat(u * n, J)
        hit = cum > thr
        first = np.r_[True, study_site[1:] != study_site[:-1]]
        # index of the first hit per site
        idx = np.full(S_, -1)
        for k in np.flatnonzero(hit)[::-1]:
            idx[study_site[k]] = k
        bj = b[idx]
        yb = a + bj + rng.normal(0, np.sqrt(s2e), S_)
        R2["b_obs_study_pred_site"].append(r2(yb, pred))
        R2["b_obs_study_pred_site_and_study"].append(r2(yb, a + bj))
        R2["b_obs_study_pred_site_with_known_b"].append(r2(yb, a + bw / n))   # best site-constant predictor knowing b
        # (c) the record-weighted site mean
        R2["c_site_mean"].append(r2(ybar, pred))
        chk_mean.append(np.var(ybar, ddof=1) - (s2a + np.mean(s2b * g.w2 + s2e / n)))
        if single.sum() >= 2:
            chk_single.append(np.var(ybar[single], ddof=1) - tot)
    ce = res["groups"][name]["ceilings"]
    o = {k: float(np.mean(v)) for k, v in R2.items()}
    o.update(ceiling_independent_study=ce["independent_study"]["estimate"],
             ceiling_same_study=ce["same_study"]["estimate"], ceiling_site_mean=ce["site_mean"]["estimate"],
             check_site_mean_var_diff_expect=float(np.mean(chk_mean)),
             check_singleton_var_diff_expect=float(np.mean(chk_single)) if chk_single else None,
             frac_sites_multi_study=float((g.n_study >= 2).mean()), n_sites=int(S_))
    out[name] = o
    print(f"== {name} (sites {S_}, multi-study share {o['frac_sites_multi_study']:.3f})")
    print(f"  (a) new study       sim R2 {o['a_new_study']:.4f}   ceiling_independent_study {o['ceiling_independent_study']:.4f}")
    print(f"  (b) observed study, pred = site effect          sim R2 {o['b_obs_study_pred_site']:.4f}")
    print(f"  (b) observed study, pred = site + study effect  sim R2 {o['b_obs_study_pred_site_and_study']:.4f}   ceiling_same_study {o['ceiling_same_study']:.4f}")
    print(f"  (b) observed study, pred = site + weighted mean of its b (best site-constant) sim R2 {o['b_obs_study_pred_site_with_known_b']:.4f}")
    print(f"  (c) site mean       sim R2 {o['c_site_mean']:.4f}   ceiling_site_mean {o['ceiling_site_mean']:.4f}")
    print(f"  E[check_site_mean_var_diff] {o['check_site_mean_var_diff_expect']:+.5f}  E[check_singleton_var_diff] {o['check_singleton_var_diff_expect']}")
json.dump(out, open("rerun_c2_sim.json", "w"), indent=1)
