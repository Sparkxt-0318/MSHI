"""Check 3c: (i) validate the closed-form REML against the dense one; (ii) reproduce, on South America bootstrap
replicate b=2 of the stage's own draws, the statsmodels boundary fit that returns llf = +inf (candidate dropped) and
show what the stage keeps vs the REML maximum; (iii) for the groups given in argv, every bootstrap replicate: the
stage's kept fit (NC.fit_nested, unchanged) vs the bounded REML maximum, and the CIs of the ceilings both ways.
Usage: c3c_fast.py <group> [<group> ...]"""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C")
import json
import warnings
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from common import REPO, reml_loglik
from fastreml import suffstats, reml_fast, reml_max
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config
from statsmodels.regression.mixed_linear_model import MixedLM

warnings.simplefilter("ignore")
cfg = load_config()
S = NC.Settings.from_cfg(cfg)
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
D = NC.draws(groups, S)
res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
q = S.quantiles

with threadpool_limits(limits=1):
    # (i) closed form == dense
    g = groups["South America"]
    y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), 2)
    ss = suffstats(y, site, study)
    for th in [(0.2, 0.05, 0.1), (0.0, 0.3, 0.1), (0.25, 0.0, 0.12), (1e-9, 1e-9, 0.3)]:
        a, b = reml_fast(th, ss), reml_loglik(th, y, site, study)[0]
        assert abs(a - b) < 1e-8, (th, a, b)
    print("closed-form REML == dense REML at 4 test points (abs diff < 1e-8)")

    # (ii) South America replicate b=2
    y, site, study = NC.replicate(g, D[2]["South America"], 2)
    fit = NC.fit_nested(y, site, study, S.optimizer)
    c = fit["candidates"]
    print("\nSouth America, bootstrap replicate b=2 (the stage's own draw):")
    for k, v in c.items():
        print(f"  {k:9s} usable {v['usable']} converged {v['converged']} llf {v['llf']} s2 ({v.get('s2_site')}, "
              f"{v.get('s2_study')}, {v.get('s2_record')}) warnings {v['warnings'][:2]}")
    th, llf = reml_max(suffstats(y, site, study), y_var=np.var(y))
    print(f"  stage keeps: {fit['chosen']} s2 ({fit['s2_site']:.6f}, {fit['s2_study']:.6f}, {fit['s2_record']:.6f}) "
          f"llf {c[fit['chosen']]['llf']:.6f}")
    print(f"  bounded REML maximum: s2 {np.round(th, 6)} llf {llf:.6f}")
    # the no_study model directly, as _fit_candidate builds it
    one = np.ones((len(y), 1))
    f = MixedLM(y, one, groups=site, exog_re=one).fit(reml=True, method="lbfgs")
    print(f"  MixedLM(groups=site, exog_re=1).fit(reml=True, method='lbfgs'): converged {f.converged} llf {f.llf} "
          f"cov_re {float(np.asarray(f.cov_re)[0,0])} scale {f.scale}")
    for meth in ["bfgs", "nm", "powell"]:
        try:
            f2 = MixedLM(y, one, groups=site, exog_re=one).fit(reml=True, method=meth)
            print(f"    same model, method {meth}: converged {f2.converged} llf {f2.llf} cov_re "
                  f"{float(np.asarray(f2.cov_re)[0,0])} scale {f2.scale}")
        except Exception as e:  # noqa: BLE001
            print(f"    same model, method {meth}: {type(e).__name__}: {e}")
    # the model's own loglike at the bounded maximum (finite) vs at cov_re = 0
    m = MixedLM(y, one, groups=site, exog_re=one)
    from statsmodels.regression.mixed_linear_model import MixedLMParams
    for rel in [th[0] / th[2], 1e-8, 0.0]:
        p = MixedLMParams.from_components(fe_params=np.zeros(1), cov_re=np.array([[rel]]))
        try:
            print(f"    statsmodels profile REML loglike at cov_re/scale = {rel:.3g}: {m.loglike(p, profile_fe=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"    loglike at {rel}: {type(e).__name__}: {e}")

    # (iii) all replicates of the requested groups
    out = {}
    for name in sys.argv[1:]:
        g = groups[name]
        rows = []
        for b, d in enumerate(D):
            draw = d[name]
            y, site, study = NC.replicate(g, draw, S.min_records)
            fit = NC.fit_nested(y, site, study, S.optimizer)
            row = {"b": b, "status": fit["status"]}
            if fit["status"] in ("ok", "failed"):
                cands = fit["candidates"]
                extra = [(v["s2_site"], v["s2_study"], v["s2_record"]) for v in cands.values()
                         if v.get("s2_site") is not None and np.isfinite([v["s2_site"], v["s2_study"], v["s2_record"]]).all()
                         and v["s2_record"] > 0]
                th, llf = reml_max(suffstats(y, site, study), extra, y_var=np.var(y))
                row["own"] = th.tolist()
                row["own_llf"] = llf
                row["dropped"] = [k for k in NC.CANDIDATES if not cands[k]["usable"]]
                row["llf_inf"] = [k for k in NC.CANDIDATES if cands[k]["llf"] is not None and np.isinf(cands[k]["llf"])]
                if fit["status"] == "ok":
                    row["kept"] = [fit["s2_site"], fit["s2_study"], fit["s2_record"]]
                    row["chosen"] = fit["chosen"]
                    row["gap"] = llf - cands[fit["chosen"]]["llf"]
                n_rec, n_study, w2 = g.n_rec[draw], g.n_study[draw], g.w2[draw]
                row["ceil_own"] = NC.ceilings(*th, n_rec, n_study, w2)
                if fit["status"] == "ok":
                    row["ceil_kept"] = NC.ceilings(*row["kept"], n_rec, n_study, w2)
            rows.append(row)
        ok = [r for r in rows if r["status"] == "ok"]
        fl = [r for r in rows if r["status"] == "failed"]
        gaps = np.array([r["gap"] for r in ok])
        print(f"\n== {name}: ok {len(ok)} failed {len(fl)} unidentified "
              f"{sum(r['status'] == 'unidentified' for r in rows)}; replicates with a candidate llf = +inf: "
              f"{sum(bool(r.get('llf_inf')) for r in rows)}; kept fit below the REML max by > 1e-3: "
              f"{int((gaps > 1e-3).sum())} (> 0.05: {int((gaps > 0.05).sum())}; max {gaps.max():.4f}); failed replicates "
              f"with a finite REML max: {len(fl)}")
        for key in ("share_site", "ceiling_same_study", "ceiling_site_mean", "share_study"):
            kept = np.array([r["ceil_kept"][key] for r in ok])
            own = np.array([r["ceil_own"][key] for r in ok + fl])
            stage = res["groups"][name]
            st = (stage["shares"][key.removeprefix("share_")] if key.startswith("share_")
                  else stage["ceilings"][key.removeprefix("ceiling_")])
            print(f"  {key:20s} stage CI {np.round(st['ci'], 4).tolist()} (n {st['n_boot_used']}) | recomputed kept "
                  f"{np.round(np.quantile(kept, q), 4).tolist()} (n {len(kept)}) | REML maxima "
                  f"{np.round(np.quantile(own, q), 4).tolist()} (n {len(own)})")
        out[name] = rows
    if sys.argv[1:]:
        json.dump(out, open("c3c_fast_" + "_".join(a.replace(" ", "") for a in sys.argv[1:]) + ".json", "w"),
                  default=float)
