"""Check 3b: re-create the stage's bootstrap draws (NC.draws, seed 7, n_boot 200) and, for the small groups, compare
each replicate's kept REML fit (the stage's candidate rule) with an own REML maximised over the closed parameter
space (L-BFGS-B on the variances, several starts). Reports replicates where the kept candidate is not the REML
maximum (llf gap), and what the CIs would be with the own maximum."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C")
import json
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits

from common import REPO, reml_loglik
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

warnings.simplefilter("ignore")
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
res = json.load(open(f"{REPO}/results/noise_ceiling.json"))


def own_max(y, site, study, extra_starts):
    tot = np.var(y)
    starts = [(0.5 * tot, 0.25 * tot, 0.25 * tot), (0.1 * tot, 0.6 * tot, 0.3 * tot), (0.8 * tot, 1e-4, 0.2 * tot),
              (1e-4, 0.8 * tot, 0.2 * tot), (1e-4, 1e-4, tot)] + extra_starts
    best = None
    for t0 in starts:
        o = minimize(lambda t: -reml_loglik(t, y, site, study)[0], t0, method="L-BFGS-B",
                     bounds=[(0, None), (0, None), (1e-8, None)], options={"maxiter": 1000, "ftol": 1e-15, "gtol": 1e-10})
        if best is None or o.fun < best.fun:
            best = o
    return best


out = {}
which = sys.argv[1:] or ["South America", "Africa", "Oceania"]
with threadpool_limits(limits=1):
    for name in which:
        g = groups[name]
        rows = []
        for b, d in enumerate(D):
            y, site, study = NC.replicate(g, d[name], S.min_records)
            fit = NC.fit_nested(y, site, study, S.optimizer)
            row = {"b": b, "status": fit["status"]}
            if fit["status"] in ("ok", "failed"):
                c = fit["candidates"]
                extra = [(v["s2_site"], v["s2_study"], max(v["s2_record"], 1e-6)) for v in c.values()
                         if v.get("s2_site") is not None and np.isfinite([v["s2_site"], v["s2_study"], v["s2_record"]]).all()]
                o = own_max(y, site, study, extra)
                row.update(own_llf=float(-o.fun), own_s2=[float(x) for x in o.x],
                           cand={k: (v["usable"], v["converged"], v["llf"], v.get("s2_site"), v.get("s2_study"),
                                     v.get("s2_record"), v["error"]) for k, v in c.items()})
                if fit["status"] == "ok":
                    row.update(chosen=fit["chosen"], kept_llf=c[fit["chosen"]]["llf"],
                               kept_s2=[fit["s2_site"], fit["s2_study"], fit["s2_record"]])
                    row["gap"] = row["own_llf"] - row["kept_llf"]
            rows.append(row)
        ok = [r for r in rows if r["status"] == "ok"]
        gaps = np.array([r["gap"] for r in ok])
        big = [r for r in ok if r["gap"] > 1e-3]
        print(f"== {name}: replicates {len(rows)}; ok {len(ok)}; failed {sum(r['status']=='failed' for r in rows)}; "
              f"unidentified {sum(r['status']=='unidentified' for r in rows)}")
        print(f"  llf gap (own REML max - kept): max {gaps.max():.4g}; > 1e-3 in {len(big)} replicates; > 0.1 in "
              f"{int((gaps > 0.1).sum())}")
        for r in big[:12]:
            print(f"   b={r['b']:3d} chosen {r['chosen']:9s} kept s2 {np.round(r['kept_s2'], 4)} llf {r['kept_llf']:.4f} | "
                  f"own s2 {np.round(r['own_s2'], 4)} llf {r['own_llf']:.4f}")
            for k, v in r["cand"].items():
                print(f"        cand {k:9s} usable {v[0]} conv {v[1]} llf {v[2]} s2 ({v[3]}, {v[4]}, {v[5]}) err {v[6]}")
        failed = [r for r in rows if r["status"] == "failed"]
        for r in failed:
            print(f"   FAILED b={r['b']}: own max s2 {np.round(r['own_s2'], 4)} llf {r['own_llf']:.4f}")
            for k, v in r["cand"].items():
                print(f"        cand {k:9s} usable {v[0]} conv {v[1]} llf {v[2]} s2 ({v[3]}, {v[4]}, {v[5]}) err {v[6]}")
        # CI of share_site with the kept fits (= stage) vs with the own maxima (failed replicates included)
        def share(s2):
            return s2[0] / sum(s2)
        kept = np.array([share(r["kept_s2"]) for r in ok])
        own = np.array([share(r["own_s2"]) for r in rows if r["status"] in ("ok", "failed")])
        q = S.quantiles
        st = res["groups"][name]["shares"]["site"]
        print(f"  share_site CI: stage {st['ci']} | recomputed from kept fits {np.quantile(kept, q).round(6).tolist()} "
              f"| own REML maxima {np.quantile(own, q).round(6).tolist()}")
        def ceil_same(s2):
            return (s2[0] + s2[1]) / sum(s2)
        kept_s = np.array([ceil_same(r["kept_s2"]) for r in ok])
        own_s = np.array([ceil_same(r["own_s2"]) for r in rows if r["status"] in ("ok", "failed")])
        st2 = res["groups"][name]["ceilings"]["same_study"]
        print(f"  same_study CI: stage {st2['ci']} | kept {np.quantile(kept_s, q).round(6).tolist()} | own "
              f"{np.quantile(own_s, q).round(6).tolist()}")
        out[name] = rows
json.dump(out, open("c3b_boot_refits_" + "_".join(w.replace(' ', '') for w in which) + ".json", "w"), default=str)
