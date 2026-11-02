"""PROXY re-run of exp_forest_bias.py (N2b). Site climate = nearest original-pipeline site; cell climate = legacy atlas.
Step 0 reproduces the handoff spec; later steps are new tests. All bootstrap draws seeded."""
import sys, json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
S, G, OUT = sys.argv[1:4]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).copy()
d["pf_1_5"] = d.code.isin([1, 2, 3, 4, 5]).astype(int)
d["pf_1_5_8"] = d.code.isin([1, 2, 3, 4, 5, 8]).astype(int)
g0 = pd.read_parquet(G)
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g0["n"] = g0[inc].sum(axis=1)
g = g0[(g0.n >= 20)].dropna(subset=["bio01", "bio12"]).copy()
g["lnP"] = np.log(g.bio12.clip(lower=1)); g["continent"] = g.cont
g["veg_area_m2"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0)
g["f_1_5"] = g[["n1", "n2", "n3", "n4", "n5"]].sum(axis=1) / g.n
g["f_1_5_8"] = g[["n1", "n2", "n3", "n4", "n5", "n8"]].sum(axis=1) / g.n
R = {"n_sites": len(d), "cells": len(g)}

def totals(s, pix="pf_1_5", fcol="f_1_5"):
    s = s.assign(pixel_forest=s[pix])
    mA = smf.ols("log_rs ~ bio01 + lnP + C(continent)", data=s).fit()
    mB = smf.ols("log_rs ~ bio01 + lnP + pixel_forest + C(continent)", data=s).fit()
    mC = smf.ols("log_rs ~ bio01 + lnP + plot_forest + C(continent)", data=s).fit()
    sm = {k: np.mean(np.exp(m.resid)) for k, m in [("A", mA), ("B", mB), ("C", mC)]}
    f = g[fcol]
    A = np.exp(mA.predict(g)) * sm["A"]
    B = f * np.exp(mB.predict(g.assign(pixel_forest=1))) * sm["B"] + (1 - f) * np.exp(mB.predict(g.assign(pixel_forest=0))) * sm["B"]
    C = f * np.exp(mC.predict(g.assign(plot_forest=1))) * sm["C"] + (1 - f) * np.exp(mC.predict(g.assign(plot_forest=0))) * sm["C"]
    tA, tB, tC = [float((v * g.veg_area_m2).sum() / 1e15) for v in (A, B, C)]
    return dict(A=tA, B=tB, C=tC, infA=tA / tC - 1, infB=tB / tC - 1, b_pix=mB.params.pixel_forest, b_plot=mC.params.plot_forest)

q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
base = totals(d)
R["step0_handoff_spec"] = {k: round(float(v), 3) for k, v in base.items()}
R["step0_plot_share"] = round(d.plot_forest.mean(), 3); R["step0_pixel_share"] = round(d.pf_1_5.mean(), 3)
R["step0_landscape_f"] = round(float(np.average(g.f_1_5, weights=g.veg_area_m2)), 3)
rng = np.random.default_rng(0)
B = []
for _ in range(500):
    s = d.iloc[rng.integers(0, len(d), len(d))]; t = totals(s); B.append((t["infA"], t["b_pix"], t["b_plot"], t["b_plot"] - t["b_pix"]))
B = np.array(B)
R["step0_iid500"] = dict(infA_ci=q(B[:, 0]), b_pix_ci=q(B[:, 1]), b_plot_ci=q(B[:, 2]), diff_plot_minus_pix_ci=q(B[:, 3]),
                         frac_draws_diff_le0=round(float((B[:, 3] <= 0).mean()), 3))
# spatial block bootstrap (blocks of deg x deg), 2000 draws
def block_boot(deg, ndraw=1000, seed=1, pix="pf_1_5", fcol="f_1_5"):
    r = np.random.default_rng(seed)
    blk = (np.floor(d.lon / deg).astype(int).astype(str) + "_" + np.floor(d.lat / deg).astype(int).astype(str)).values
    ub = np.unique(blk); groups = {b: np.where(blk == b)[0] for b in ub}
    out = []
    for _ in range(ndraw):
        pick = r.choice(ub, len(ub)); ix = np.concatenate([groups[b] for b in pick])
        t = totals(d.iloc[ix], pix, fcol); out.append((t["infA"], t["b_pix"], t["b_plot"], t["b_plot"] - t["b_pix"]))
    out = np.array(out)
    return dict(n_blocks=len(ub), infA_ci=q(out[:, 0]), b_pix_ci=q(out[:, 1]), b_plot_ci=q(out[:, 2]), diff_ci=q(out[:, 3]),
                frac_b_plot_le0=round(float((out[:, 2] <= 0).mean()), 3))
R["block2deg"] = block_boot(2.0)
R["block5deg"] = block_boot(5.0)
# alternative crosswalk: IGBP 8 counted as forest for both the pixel flag and the landscape fraction
alt = totals(d, "pf_1_5_8", "f_1_5_8")
R["alt_crosswalk_1_5_8"] = {k: round(float(v), 3) for k, v in alt.items()}
R["alt_crosswalk_1_5_8"]["pixel_share"] = round(d.pf_1_5_8.mean(), 3)
R["alt_crosswalk_1_5_8"]["landscape_f"] = round(float(np.average(g.f_1_5_8, weights=g.veg_area_m2)), 3)
Ba = []
rng = np.random.default_rng(0)
for _ in range(500):
    s = d.iloc[rng.integers(0, len(d), len(d))]; t = totals(s, "pf_1_5_8", "f_1_5_8"); Ba.append((t["infA"], t["b_pix"]))
Ba = np.array(Ba); R["alt_crosswalk_1_5_8"]["iid500_infA_ci"] = q(Ba[:, 0]); R["alt_crosswalk_1_5_8"]["iid500_b_pix_ci"] = q(Ba[:, 1])
R["alt_block2deg"] = block_boot(2.0, pix="pf_1_5_8", fcol="f_1_5_8")
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps(R, indent=1))
