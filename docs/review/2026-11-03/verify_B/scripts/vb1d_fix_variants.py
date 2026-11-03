"""B-1 check (d): which fix is correct. On the synthetic stand-in training sets of vb1b that hit large alphas, compare
with the exact AIC-optimal model (vb1_common.exact_aic_search + Exact):
  (i) post-hoc clip: fit_gam's selected alpha clipped to <= 1e8 and refitted (statsmodels);
  (ii) bounded search: log alpha capped at log 1e8 inside the NM objective (vb1_common.clipped_search).
Reports max |fitted difference| and the test-set r2 differences (transfer rows: every other continent; block folds:
the held-out fold). Also counts, on the reviewer's own synthetic data (synthA), how many of the 49 training sets of
their s26 end with a selected alpha >= 1e13 (the claim '37 of 49 ... end in this range')."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/scripts")
import warnings
import numpy as np
import pandas as pd
from statsmodels.gam.api import GLMGam
from vb1_common import standin_sites, basis, Exact, exact_aic_search, clipped_search
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.spatial import block_folds

warnings.simplefilter("ignore")
cfg = load_config()
spec = T.Spec.from_cfg(cfg)
g = spec.gam
s = standin_sites()
rng = np.random.default_rng(2026)
syn = s.copy()
syn["log_rs"] = (4.2 + 0.09 * syn.bio01 - 0.0018 * syn.bio01 ** 2 + 0.9 * np.log(syn.bio12)
                 - 0.05 * np.log(syn.bio12) ** 2 + rng.normal(0, 0.45, len(syn)))
conts = cfg["phase2"]["continents"]


def pred(params, bs, Xt):
    Bt = np.hstack([T.spline_basis(sm, Xt[:, j]) for j, sm in enumerate(bs.smoothers)])
    return params[0] + Bt @ np.asarray(params)[1:]


cases = [("pairwise:South America", syn[syn.continent_geo == "South America"],
          [syn[syn.continent_geo == c] for c in conts if c != "South America"]),
         ("pairwise:North America", syn[syn.continent_geo == "North America"],
          [syn[syn.continent_geo == c] for c in conts if c != "North America"])]
for c in ("Europe", "North America"):
    sub = syn[syn.continent_geo == c].reset_index(drop=True)
    for seed in (42, 43, 44):
        for k, (tr, va) in enumerate(block_folds(sub.lon.values, sub.lat.values, seed, 5.0, 5)):
            cases.append((f"blocks:{c}:s{seed}f{k}", sub.iloc[tr], [sub.iloc[va]]))
worst = {"clip": (0, 0), "bounded": (0, 0)}
n_big = 0
for name, tr, tests in cases:
    m = T.fit_gam(spec, tr)
    a = np.array(m.info["alpha"])
    if a.max() < 1e12:
        continue
    n_big += 1
    X, y, bs = basis(spec, tr)
    ex = Exact(X, y, bs, exact_aic_search(X, y, bs))
    clip = GLMGam(y, exog=np.ones((len(y), 1)), smoother=bs, alpha=np.minimum(a, 1e8)).fit()
    a_b, bnd = clipped_search(y, bs, np.log(1e8))
    out = {}
    for lab, res in (("clip", clip), ("bounded", bnd)):
        dfit = float(np.max(np.abs(res.fittedvalues - ex.fitted)))
        dr2 = max((abs(T.r2(te.log_rs, pred(res.params, bs, T.design(te, g["features"], g["log"])))
                       - T.r2(te.log_rs, ex.predict_x(T.design(te, g["features"], g["log"])))) for te in tests), default=0)
        out[lab] = (dfit, dr2)
        worst[lab] = (max(worst[lab][0], dfit), max(worst[lab][1], dr2))
    print(f"{name:26s} fit_gam alpha {['%.1e' % v for v in a]} | clip: max|fit diff| {out['clip'][0]:.1e} max|r2 diff| "
          f"{out['clip'][1]:.1e} | bounded: {out['bounded'][0]:.1e} / {out['bounded'][1]:.1e} (alpha {['%.1e' % v for v in a_b]})",
          flush=True)
print(f"\n{n_big} training sets with alpha >= 1e12; worst vs the exact AIC-optimal model: post-hoc clip {worst['clip'][0]:.2e} "
      f"(fit), {worst['clip'][1]:.2e} (r2); bounded search {worst['bounded'][0]:.2e} (fit), {worst['bounded'][1]:.2e} (r2)")

# the reviewer's data: alpha ranges over their 49 training sets (as in their s26)
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/"
                        "out/data/interim/features_analysis_qc.parquet").sort_values("site_id").reset_index(drop=True)
rows = []
for c in ("Europe", "Asia", "North America"):
    sub = synth[synth.continent_geo == c].reset_index(drop=True)
    for sd in (42, 43, 44):
        for k, (trn, va) in enumerate(block_folds(sub.lon.values, sub.lat.values, sd, 5.0, 5)):
            rows.append(sub.iloc[trn])
for tr_c in ("Asia", "Europe", "North America", "South America"):
    rows.append(synth[synth.continent_geo == tr_c])
mx = np.array([max(T.fit_gam(spec, r).info["alpha"]) for r in rows])
print(f"\nreviewer's synthA, {len(rows)} training sets: max alpha >= 1e13: {int((mx >= 1e13).sum())}; >= 1e14: "
      f"{int((mx >= 1e14).sum())}; in [1e14, 1.6e15]: {int(((mx >= 1e14) & (mx <= 1.6e15)).sum())}; "
      f"log10 range {np.log10(mx.min()):.1f}..{np.log10(mx.max()):.1f}")
