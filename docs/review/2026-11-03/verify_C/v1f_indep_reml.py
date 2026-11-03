"""Verifier's independent check of C-1 (not the reviewer's code): REML maximum of the nested model by a dense,
scale-profiled REML on a 2-D grid of variance ratios (gamma_site, gamma_study >= 0, zeros included) followed by local
refinement (interior and both faces), for every bootstrap replicate of a group. The stage's own code is used only to
build the replicates (NC.draws, NC.replicate) and to get the stage's kept fit (NC.fit_nested, unchanged).

V = s2_rec * H, H = I + ga * A + gb * B (A: same-site indicator, B: same-study indicator).
Profiled REML: l(ga, gb) = -0.5 * [(N-1) * (log(2 pi s2hat) + 1) + log|H| + log(1'H^-1 1)],
s2hat = r'H^-1 r / (N-1), r = y - 1 * beta_hat (GLS).
Usage: v1_indep_reml.py <group> [max_b]
"""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen")
import json
import time
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from threadpoolctl import threadpool_limits

from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config

warnings.simplefilter("ignore")
REPO = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C/frozen"
OUT = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_C"


class Prof:
    def __init__(self, y, site, study):
        self.y = np.asarray(y, float)
        self.N = len(y)
        self.A = (site[:, None] == site[None, :]).astype(float)
        self.B = (study[:, None] == study[None, :]).astype(float)
        self.I = np.eye(self.N)
        self.R = np.stack([np.ones(self.N), self.y], axis=1)   # (N, 2)

    def batch(self, ga, gb):
        """profiled REML and s2hat for arrays ga, gb (same shape (K,))."""
        H = self.I[None] + ga[:, None, None] * self.A[None] + gb[:, None, None] * self.B[None]
        L = np.linalg.cholesky(H)
        Z = np.linalg.solve(L, np.broadcast_to(self.R, (len(ga), self.N, 2)))
        z1, zy = Z[:, :, 0], Z[:, :, 1]
        a11 = np.einsum("kn,kn->k", z1, z1)
        a1y = np.einsum("kn,kn->k", z1, zy)
        ayy = np.einsum("kn,kn->k", zy, zy)
        rr = ayy - a1y ** 2 / a11
        s2 = rr / (self.N - 1)
        logdet = 2 * np.log(np.diagonal(L, axis1=1, axis2=2)).sum(axis=1)
        ll = -0.5 * ((self.N - 1) * (np.log(2 * np.pi * s2) + 1) + logdet + np.log(a11))
        return ll, s2

    def one(self, ga, gb):
        if ga < 0 or gb < 0:
            return -np.inf, np.nan
        ll, s2 = self.batch(np.array([ga]), np.array([gb]))
        return float(ll[0]), float(s2[0])

    def full(self, s2a, s2b, s2e):
        """unprofiled REML log-likelihood at (s2_site, s2_study, s2_record)."""
        V = s2e * self.I + s2a * self.A + s2b * self.B
        L = np.linalg.cholesky(V)
        Z = np.linalg.solve(L, self.R)
        z1, zy = Z[:, 0], Z[:, 1]
        a11, a1y, ayy = z1 @ z1, z1 @ zy, zy @ zy
        rr = ayy - a1y ** 2 / a11
        return float(-0.5 * ((self.N - 1) * np.log(2 * np.pi) + 2 * np.log(np.diag(L)).sum() + np.log(a11) + rr))


def reml_max(p: Prof):
    grid = np.r_[0.0, np.geomspace(1e-4, 1e3, 70)]
    GA, GB = np.meshgrid(grid, grid, indexing="ij")
    ga, gb = GA.ravel(), GB.ravel()
    ll = np.empty(len(ga))
    for a in range(0, len(ga), 400):
        ll[a:a + 400] = p.batch(ga[a:a + 400], gb[a:a + 400])[0]
    cands = []
    k = int(np.argmax(ll))
    cands.append((ll[k], ga[k], gb[k]))
    # interior refinement on sqrt scale (reaches zeros), from the best grid point and from the best of each face
    for face in ("all", "ga0", "gb0"):
        m = {"all": np.ones_like(ga, bool), "ga0": ga == 0, "gb0": gb == 0}[face]
        kk = int(np.flatnonzero(m)[np.argmax(ll[m])])
        x0 = np.sqrt([ga[kk], gb[kk]])
        o = minimize(lambda x: -p.one(x[0] ** 2, x[1] ** 2)[0], x0, method="Nelder-Mead",
                     options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 4000})
        cands.append((-o.fun, o.x[0] ** 2, o.x[1] ** 2))
        o = minimize(lambda x: -p.one(x[0], x[1])[0], [ga[kk], gb[kk]], method="L-BFGS-B",
                     bounds=[(0, None), (0, None)], options={"ftol": 1e-15, "gtol": 1e-10, "maxiter": 2000})
        cands.append((-o.fun, o.x[0], o.x[1]))
    # the faces by bounded 1-D search
    hi = 1e3
    for face in ("ga0", "gb0"):
        f = (lambda t: -p.one(0.0, t)[0]) if face == "ga0" else (lambda t: -p.one(t, 0.0)[0])
        o = minimize_scalar(f, bounds=(0.0, hi), method="bounded", options={"xatol": 1e-12})
        # also a log-scale search near small values
        o2 = minimize_scalar(lambda u: f(np.exp(u)), bounds=(np.log(1e-8), np.log(hi)), method="bounded",
                             options={"xatol": 1e-12})
        for t, v in ((o.x, -o.fun), (np.exp(o2.x), -o2.fun)):
            cands.append((v, 0.0, t) if face == "ga0" else (v, t, 0.0))
        cands.append((p.one(0.0, 0.0)[0], 0.0, 0.0))
    best = max(cands, key=lambda c: c[0])
    llb, a, b = best
    s2 = p.one(a, b)[1]
    return {"llf": float(llb), "s2": [a * s2, b * s2, s2], "gamma": [a, b], "grid_best": float(ll.max())}


def main():
    name = sys.argv[1]
    max_b = int(sys.argv[2]) if len(sys.argv) > 2 else None
    cfg = load_config()
    S = NC.Settings.from_cfg(cfg)
    rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
    sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_qc.parquet")
    rr, sst, info = NC.prepare(rec, sites, S)
    groups = NC.build_groups(rr, sst, S.continents)
    D = NC.draws(groups, S)
    res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
    g = groups[name]
    q = S.quantiles
    rows = []
    t0 = time.time()
    with threadpool_limits(limits=1):
        # constant check against statsmodels' llf on the point fit
        y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), S.min_records)
        fit = NC.fit_nested(y, site, study, S.optimizer)
        p = Prof(y, site, study)
        c = fit["candidates"][fit["chosen"]]
        mine_at_sm = p.full(c["s2_site"], c["s2_study"], c["s2_record"])
        mx = reml_max(p)
        print(f"{name} point fit: stage kept {fit['chosen']} s2 ({c['s2_site']:.6f}, {c['s2_study']:.6f}, "
              f"{c['s2_record']:.6f}) statsmodels llf {c['llf']:.6f}; my REML at those s2 {mine_at_sm:.6f}; "
              f"my max s2 {np.round(mx['s2'], 6).tolist()} llf {mx['llf']:.6f}", flush=True)
        for b, d in enumerate(D[:max_b] if max_b else D):
            draw = d[name]
            y, site, study = NC.replicate(g, draw, S.min_records)
            fit = NC.fit_nested(y, site, study, S.optimizer)
            row = {"b": b, "status": fit["status"]}
            if fit["status"] in ("ok", "failed"):
                p = Prof(y, site, study)
                mx = reml_max(p)
                row["mine"] = mx
                cands = fit["candidates"]
                row["cand"] = {k: {"usable": v["usable"], "converged": v["converged"], "llf": v["llf"],
                                   "s2": [v.get("s2_site"), v.get("s2_study"), v.get("s2_record")],
                                   "error": v["error"]} for k, v in cands.items()}
                row["llf_inf"] = [k for k, v in cands.items() if v["llf"] is not None and np.isinf(v["llf"])]
                row["raised"] = [k for k, v in cands.items() if v["error"]]
                if fit["status"] == "ok":
                    kept = [fit["s2_site"], fit["s2_study"], fit["s2_record"]]
                    row["chosen"] = fit["chosen"]
                    row["kept"] = kept
                    row["kept_llf_sm"] = cands[fit["chosen"]]["llf"]
                    row["kept_llf_mine"] = p.full(*kept)
                    row["gap"] = mx["llf"] - row["kept_llf_mine"]
                    row["ceil_kept"] = NC.ceilings(*kept, g.n_rec[draw], g.n_study[draw], g.w2[draw])
                row["ceil_mine"] = NC.ceilings(*mx["s2"], g.n_rec[draw], g.n_study[draw], g.w2[draw])
            rows.append(row)
    ok = [r for r in rows if r["status"] == "ok"]
    fl = [r for r in rows if r["status"] == "failed"]
    gaps = np.array([r["gap"] for r in ok])
    print(f"== {name}: {len(rows)} replicates in {time.time() - t0:.0f} s; ok {len(ok)} failed {len(fl)} "
          f"unidentified {sum(r['status'] == 'unidentified' for r in rows)}")
    print(f"  replicates with a candidate llf=+inf: {sum(bool(r.get('llf_inf')) for r in rows)} "
          f"(b = {[r['b'] for r in rows if r.get('llf_inf')]})")
    print(f"  replicates with a candidate that raised: {sum(bool(r.get('raised')) for r in rows)} "
          f"(b = {[r['b'] for r in rows if r.get('raised')]})")
    print(f"  kept fit below my REML max by > 1e-3: {int((gaps > 1e-3).sum())}, > 0.05: {int((gaps > 0.05).sum())}, "
          f"max gap {gaps.max():.4f}; my max below kept by > 1e-6 (my optimiser worse): {int((gaps < -1e-6).sum())} "
          f"(min gap {gaps.min():.2e})")
    for r in ok:
        if r["gap"] > 1e-3:
            print(f"   b={r['b']:3d} kept {r['chosen']:8s} s2 {np.round(r['kept'], 4).tolist()} llf(mine) "
                  f"{r['kept_llf_mine']:.4f} (sm {r['kept_llf_sm']:.4f}) | my max s2 {np.round(r['mine']['s2'], 4).tolist()} "
                  f"llf {r['mine']['llf']:.4f} | share_site kept {r['ceil_kept']['share_site']:.4f} max "
                  f"{r['ceil_mine']['share_site']:.4f}; dropped/inf {r['llf_inf']} raised {r['raised']}")
    for r in fl:
        print(f"   FAILED b={r['b']}: my max s2 {np.round(r['mine']['s2'], 4).tolist()} llf {r['mine']['llf']:.4f} "
              f"share_site {r['ceil_mine']['share_site']:.4f}; candidates "
              + "; ".join(f"{k}: conv {v['converged']} llf {v['llf']} err {v['error']}" for k, v in r["cand"].items()))
    stage = res["groups"][name]
    for key in ("share_site", "share_study", "ceiling_independent_study", "ceiling_same_study", "ceiling_site_mean",
                "ceiling_site_mean_equal_study_weights"):
        st = (stage["shares"][key.removeprefix("share_")] if key.startswith("share_")
              else stage["ceilings"][key.removeprefix("ceiling_")])
        kept = np.array([r["ceil_kept"][key] for r in ok])
        mine = np.array([r["ceil_mine"][key] for r in ok + fl])
        ck, cm = np.quantile(kept, q), np.quantile(mine, q)
        print(f"  {key:38s} committed {np.round(st['ci'], 4).tolist()} n {st['n_boot_used']} | stage recomputed "
              f"{np.round(ck, 4).tolist()} n {len(kept)} | my REML maxima {np.round(cm, 4).tolist()} n {len(mine)} | "
              f"diff lo {cm[0] - st['ci'][0]:+.4f} hi {cm[1] - st['ci'][1]:+.4f}")
    json.dump(rows, open(f"{OUT}/v1_indep_reml_{name.replace(' ', '')}.json", "w"), default=float)


if __name__ == "__main__":
    main()
