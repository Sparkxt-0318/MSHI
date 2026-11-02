"""Verifier's numpy re-implementation of the N2b spec (exp_forest_bias.py L58-69) + alternatives, on PROXY climate.
Bootstraps: iid site (as handoff) and 2-deg block. Outputs JSON."""
import sys, json, numpy as np, pandas as pd
import statsmodels.api as sm
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, cells, V
NB = int(sys.argv[1]); SFILL = sys.argv[2] == "fill"; CFILL = sys.argv[3] == "fill"; TAG = sys.argv[4]
d = sites(fill=SFILL); g = cells(fill=CFILL)
d["na"] = (d.continent == "North America").astype(float); g["na"] = (g.continent == "North America").astype(float)
d["W8"] = np.isin(d.code, [1, 2, 3, 4, 5, 8]).astype(float); d["W"] = d.pixel_forest.astype(float); d["X"] = d.plot_forest.astype(float)
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); area = g.veg_area_m2.values
def ols(Xm, y):
    b = np.linalg.lstsq(Xm, y, rcond=None)[0]; return b, y - Xm @ b
def stats(s, fcol="f", wcol="W"):
    y = s.log_rs.values; Z = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na]); X = s.X.values; W = s[wcol].values
    f = g[fcol].values
    bA, rA = ols(Z, y); bB, rB = ols(np.column_stack([Z, W]), y); bC, rC = ols(np.column_stack([Z, X]), y)
    bBC, _ = ols(np.column_stack([Z, X, W]), y)                      # both flags (surrogacy check)
    smA, smB, smC = np.exp(rA).mean(), np.exp(rB).mean(), np.exp(rC).mean()
    smCf, smCn = np.exp(rC[X == 1]).mean(), np.exp(rC[X == 0]).mean()  # class-specific smearing
    A = (np.exp(Gz @ bA) * smA * area).sum()
    B = ((f * np.exp(Gz @ bB[:4] + bB[4]) + (1 - f) * np.exp(Gz @ bB[:4])) * smB * area).sum()
    C = ((f * np.exp(Gz @ bC[:4] + bC[4]) + (1 - f) * np.exp(Gz @ bC[:4])) * smC * area).sum()
    Ccs = ((f * np.exp(Gz @ bC[:4] + bC[4]) * smCf + (1 - f) * np.exp(Gz @ bC[:4]) * smCn) * area).sum()
    lam = ols(np.column_stack([Z, W]), X)[0][4]                      # lambda: slope of E[X | W, Z]
    return dict(infl_A=A / C - 1, infl_B=B / C - 1, infl_A_classsmear=A / Ccs - 1, b_pix=bB[4], b_plot=bC[4], diff_plot_minus_pix=bC[4] - bB[4],
                lam=lam, expected_attenuated=lam * bC[4], b_pix_given_plot=bBC[5], arith_forest_effect=bC[4] + np.log(smCf / smCn),
                smA=smA, smC=smC, smCf=smCf, smCn=smCn, sd_res_f=rC[X == 1].std(ddof=1), sd_res_n=rC[X == 0].std(ddof=1),
                A_PgC=A / 1e15, C_PgC=C / 1e15, Ccs_PgC=Ccs / 1e15)
def glm(s, fam, fcol="f"):
    Z = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na]); y = np.exp(s.log_rs.values); f = g[fcol].values
    mA = sm.GLM(y, Z, family=fam).fit(scale="X2"); mC = sm.GLM(y, np.column_stack([Z, s.X.values]), family=fam).fit(scale="X2", cov_type="HC3")
    bA, bC = mA.params, mC.params
    A = (np.exp(Gz @ bA) * area).sum(); C = ((f * np.exp(Gz @ bC[:4] + bC[4]) + (1 - f) * np.exp(Gz @ bC[:4])) * area).sum()
    return dict(infl=A / C - 1, b_forest=bC[4], b_forest_ci_hc3=[float(x) for x in mC.conf_int()[4]])
deg = 2.0
blk = (np.floor(d.lon / deg).astype(int).astype(str) + "_" + np.floor(d.lat / deg).astype(int).astype(str)).values
ub = np.unique(blk); gi = {b: np.where(blk == b)[0] for b in ub}
q = lambda x: [round(float(np.nanquantile(x, .025)), 3), round(float(np.nanquantile(x, .975)), 3)]
R = {"n_sites": len(d), "cells": len(g), "n_blocks_2deg": len(ub)}
for name, fcol, wcol in [("crosswalk_1_5", "f", "W"), ("crosswalk_1_5_8", "f8", "W8")]:
    base = stats(d, fcol, wcol)
    rng = np.random.default_rng(0); I = [stats(d.iloc[rng.integers(0, len(d), len(d))], fcol, wcol) for _ in range(NB)]
    rng = np.random.default_rng(1); K = [stats(d.iloc[np.concatenate([gi[x] for x in rng.choice(ub, len(ub))])], fcol, wcol) for _ in range(NB)]
    out = {}
    for k in base:
        out[k] = round(float(base[k]), 4)
        if k in ("infl_A", "infl_B", "infl_A_classsmear", "b_pix", "b_plot", "diff_plot_minus_pix", "lam", "expected_attenuated", "b_pix_given_plot", "arith_forest_effect"):
            out[k + "_iid"] = q([x[k] for x in I]); out[k + "_block2"] = q([x[k] for x in K])
    out["landscape_share"] = round(float(np.average(g[fcol], weights=g.veg_area_m2)), 4)
    out["pixel_share_at_plots"] = round(float(d[wcol].mean()), 4)
    R[name] = out
# GLMs (handoff crosswalk), point + HC3 + iid bootstrap of inflation
for fam_name, fam in [("quasipoisson_log", sm.families.Poisson()), ("gamma_log", sm.families.Gamma(sm.families.links.Log()))]:
    b = glm(d, fam); rng = np.random.default_rng(2)
    bs = [glm(d.iloc[rng.integers(0, len(d), len(d))], fam)["infl"] for _ in range(min(NB, 500))]
    R[fam_name] = dict(infl=round(float(b["infl"]), 4), infl_iid=q(bs), b_forest=round(float(b["b_forest"]), 4), b_forest_ci_hc3=[round(x, 3) for x in b["b_forest_ci_hc3"]])
# Brown-Forsythe on C-model residuals by class
from scipy.stats import levene
y = d.log_rs.values; Z = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na, d.X]); r = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
R["brown_forsythe_p"] = float(levene(r[d.X == 1], r[d.X == 0], center="median").pvalue)
json.dump(R, open(f"{V}/out/n2b_fast_{TAG}.json", "w"), indent=1); print(json.dumps(R, indent=1))
