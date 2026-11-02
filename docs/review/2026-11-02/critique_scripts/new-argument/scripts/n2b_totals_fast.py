"""PROXY N2b totals (exp_forest_bias.py L58-86 spec, numpy OLS): inflation A/C-1 and B/C-1, iid and 2-deg block bootstrap,
and the alternative crosswalk (IGBP 8 = forest for both the pixel flag and the landscape fraction)."""
import sys, json, numpy as np, pandas as pd
S, G, OUT = sys.argv[1:4]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
d["W"] = d.code.isin([1, 2, 3, 4, 5]).astype(float); d["W8"] = d.code.isin([1, 2, 3, 4, 5, 8]).astype(float)
d["X"] = d.plot_forest.astype(float); d["na"] = (d.continent == "North America").astype(float)
g0 = pd.read_parquet(G)
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g0["n"] = g0[inc].sum(axis=1)
g = g0[g0.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
g["lnP"] = np.log(g.bio12.clip(lower=1)); g["na"] = (g.cont == "North America").astype(float)
g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0)
g["f"] = g[["n1", "n2", "n3", "n4", "n5"]].sum(axis=1) / g.n
g["f8"] = g[["n1", "n2", "n3", "n4", "n5", "n8"]].sum(axis=1) / g.n
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); area = g.area.values
def fit(Xm, y):
    b = np.linalg.lstsq(Xm, y, rcond=None)[0]; return b, np.mean(np.exp(y - Xm @ b))
def totals(s, wcol="W", fcol="f"):
    y = s.log_rs.values; Zs = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na])
    bA, smA = fit(Zs, y); bB, smB = fit(np.column_stack([Zs, s[wcol]]), y); bC, smC = fit(np.column_stack([Zs, s.X]), y)
    f = g[fcol].values
    A = np.exp(Gz @ bA) * smA
    B = (f * np.exp(Gz @ bB[:4] + bB[4]) + (1 - f) * np.exp(Gz @ bB[:4])) * smB
    C = (f * np.exp(Gz @ bC[:4] + bC[4]) + (1 - f) * np.exp(Gz @ bC[:4])) * smC
    tA, tB, tC = [(v * area).sum() / 1e15 for v in (A, B, C)]
    return np.array([tA / tC - 1, tB / tC - 1, bB[4], bC[4], tA, tC])
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
deg = 2.0
blk = (np.floor(d.lon / deg).astype(int).astype(str) + "_" + np.floor(d.lat / deg).astype(int).astype(str)).values
ub = np.unique(blk); gi = {b: np.where(blk == b)[0] for b in ub}
R = {"n": len(d), "cells": len(g), "landscape_f": round(float(np.average(g.f, weights=g.area)), 3),
     "landscape_f8": round(float(np.average(g.f8, weights=g.area)), 3)}
for name, wcol, fcol in [("handoff_crosswalk_1_5", "W", "f"), ("alt_crosswalk_1_5_8", "W8", "f8")]:
    b = totals(d, wcol, fcol)
    rng = np.random.default_rng(0); I = np.array([totals(d.iloc[rng.integers(0, len(d), len(d))], wcol, fcol) for _ in range(2000)])
    rng = np.random.default_rng(1); K = np.array([totals(d.iloc[np.concatenate([gi[x] for x in rng.choice(ub, len(ub))])], wcol, fcol) for _ in range(2000)])
    R[name] = dict(infl_A=round(float(b[0]), 3), infl_A_iid=q(I[:, 0]), infl_A_block2=q(K[:, 0]),
                   infl_B=round(float(b[1]), 3), b_pix=round(float(b[2]), 3), b_pix_iid=q(I[:, 2]), b_plot=round(float(b[3]), 3),
                   b_plot_iid=q(I[:, 3]), b_plot_block2=q(K[:, 3]), A_PgC=round(float(b[4]), 2), C_PgC=round(float(b[5]), 2),
                   reduction_1_minus_C_over_A=round(float(1 - b[5] / b[4]), 3))
json.dump(R, open(OUT, "w"), indent=1); print(json.dumps(R, indent=1))
