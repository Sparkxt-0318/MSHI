"""B-1 check (b): where fit_gam's AIC search (the real code) ends on stand-in data, and what the numerical error does
to the fit and to test r2. Stand-in: real analysis-QC site coordinates and continents, SRDB-reported MAT/MAP site
means for bio01/bio12. Outcomes: (R) the real site log Rs, used ONLY for training and test sets without Europe
(Asia, North America [exploratory], South America; Africa/Oceania as tests); (S) a synthetic outcome with a nonlinear
MAT effect and a saturating ln MAP effect (all continents). Training sets: pairwise transfer training continents
with >= 30 sites, LOCO (S only), and 5-degree block CV folds (seeds 42-44) of continents with >= 60 sites.
For each: fit_gam's alpha; max |fit_gam - exact| on the training fit at the SAME alpha (my reference, vb1_common);
the exact-AIC search's alpha and fit; the capped search (statsmodels, log alpha <= log 1e8); r2 on test sets."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/scripts")
import time
import warnings
import numpy as np
import pandas as pd
from vb1_common import standin_sites, basis, Exact, exact_aic_search, clipped_search
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.spatial import block_folds
from statsmodels.tools.sm_exceptions import SingularMatrixWarning

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


def sets_for(d, outcome):
    out = []
    allowed = [c for c in conts if outcome == "S" or c != "Europe"]
    for table, label, trc, tests in T._settings(conts):
        if any(c not in allowed for c in trc):
            continue
        tr = d[d.continent_geo.isin(trc)]
        if len(tr) < 30:
            continue
        out.append((f"{table}:{label}", tr, [d[d.continent_geo == c] for c in tests if c in allowed]))
    for c in allowed:
        sub = d[d.continent_geo == c].reset_index(drop=True)
        if len(sub) < 60:
            continue
        for seed in (42, 43, 44):
            for k, (tr, va) in enumerate(block_folds(sub.lon.values, sub.lat.values, seed, 5.0, 5)):
                out.append((f"blocks:{c}:s{seed}f{k}", sub.iloc[tr], [sub.iloc[va]]))
    return out


rows = []
for outcome, d in (("R", s), ("S", syn)):
    for name, tr, tests in sets_for(d, outcome):
        t0 = time.time()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m = T.fit_gam(spec, tr)
        n_warn = sum(issubclass(x.category, SingularMatrixWarning) for x in w)
        X, y, bs = basis(spec, tr)
        a_sel = np.array(m.info["alpha"])
        ex_same = Exact(X, y, bs, a_sel)
        a_ex = exact_aic_search(X, y, bs)
        ex_opt = Exact(X, y, bs, a_ex)
        a_cap, res_cap = clipped_search(y, bs, np.log(1e8))
        fit_cur = m.predict(tr)
        r2d_same, r2d_opt, r2d_cap, dpred = [], [], [], []
        for te in tests:
            yt = te[spec.target].to_numpy(float)
            Xt = T.design(te, g["features"], g["log"])
            p_cur = m.predict(te)
            p_same, p_opt = ex_same.predict_x(Xt), ex_opt.predict_x(Xt)
            Bt = np.hstack([T.spline_basis(sm, Xt[:, j]) for j, sm in enumerate(bs.smoothers)])
            p_cap = res_cap.params[0] + Bt @ np.asarray(res_cap.params)[1:]
            dpred.append(np.max(np.abs(p_cur - p_opt)))
            r2d_same.append(T.r2(yt, p_cur) - T.r2(yt, p_same))
            r2d_opt.append(T.r2(yt, p_cur) - T.r2(yt, p_opt))
            r2d_cap.append(T.r2(yt, p_cap) - T.r2(yt, p_opt))
        rows.append({"outcome": outcome, "set": name, "n": len(y), "alpha_sel": a_sel, "alpha_exact_search": a_ex,
                     "max_log10_alpha_sel": float(np.log10(a_sel.max())), "sm_warnings": n_warn,
                     "fit_dev_same_alpha": float(np.max(np.abs(fit_cur - ex_same.fitted))),
                     "fit_dev_vs_exact_search": float(np.max(np.abs(fit_cur - ex_opt.fitted))),
                     "cap_dev_vs_exact_search": float(np.max(np.abs(res_cap.fittedvalues - ex_opt.fitted))),
                     "aic_sm": m.info["aic"], "aic_exact_at_sel": ex_same.aic, "aic_exact_opt": ex_opt.aic,
                     "edf_sm": m.info["edf"], "edf_exact_at_sel": ex_same.edf,
                     "test_pred_dev_vs_exact_search": float(max(dpred)) if dpred else np.nan,
                     "r2diff_same_alpha": float(max(r2d_same, key=abs)) if r2d_same else np.nan,
                     "r2diff_vs_exact_search": float(max(r2d_opt, key=abs)) if r2d_opt else np.nan,
                     "r2diff_cap_vs_exact_search": float(max(r2d_cap, key=abs)) if r2d_cap else np.nan,
                     "sec": time.time() - t0})
        r = rows[-1]
        print(f"{outcome} {name:28s} n={r['n']:4d} alpha_sel={['%.1e' % v for v in a_sel]} "
              f"exact-search alpha={['%.1e' % v for v in a_ex]} dev(same alpha)={r['fit_dev_same_alpha']:.1e} "
              f"dev(vs exact search)={r['fit_dev_vs_exact_search']:.1e} cap dev={r['cap_dev_vs_exact_search']:.1e} "
              f"aic sm {r['aic_sm']:.3f} exact@sel {r['aic_exact_at_sel']:.3f} exact opt {r['aic_exact_opt']:.3f} "
              f"r2diff {r['r2diff_vs_exact_search']:+.4f} cap r2diff {r['r2diff_cap_vs_exact_search']:+.1e} warn {n_warn}",
              flush=True)

df = pd.DataFrame(rows)
df.to_pickle("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_B/work/vb1b_rows.pkl")
for outcome, gdf in df.groupby("outcome"):
    print(f"\n=== outcome {outcome}: {len(gdf)} training sets")
    print("selected max alpha >= 1e12:", int((gdf.max_log10_alpha_sel >= 12).sum()),
          "; >= 1e13:", int((gdf.max_log10_alpha_sel >= 13).sum()), "; >= 1e14:", int((gdf.max_log10_alpha_sel >= 14).sum()),
          "; range of max log10 alpha:", round(gdf.max_log10_alpha_sel.min(), 1), "..", round(gdf.max_log10_alpha_sel.max(), 1))
    print("max |fit_gam - exact| at the same alpha (training):", f"{gdf.fit_dev_same_alpha.max():.2e}",
          "; sets > 1e-3:", int((gdf.fit_dev_same_alpha > 1e-3).sum()), "; > 1e-2:", int((gdf.fit_dev_same_alpha > 1e-2).sum()))
    print("max |fit_gam - exact AIC-search model| (training):", f"{gdf.fit_dev_vs_exact_search.max():.2e}",
          "; max test-prediction difference:", f"{gdf.test_pred_dev_vs_exact_search.max():.2e}")
    print("max |r2(fit_gam) - r2(exact AIC-search model)| on test sets:", f"{gdf.r2diff_vs_exact_search.abs().max():.4f}")
    print("capped search (alpha <= 1e8): max |fit - exact AIC-search model|:", f"{gdf.cap_dev_vs_exact_search.max():.2e}",
          "; max |r2 diff|:", f"{gdf.r2diff_cap_vs_exact_search.abs().max():.2e}")
    print("SingularMatrixWarnings per fit_gam call: total", int(gdf.sm_warnings.sum()), "max", int(gdf.sm_warnings.max()))
