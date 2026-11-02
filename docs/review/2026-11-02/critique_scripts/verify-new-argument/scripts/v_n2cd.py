"""Verifier's PROXY re-run of N2d (exp_poststrat_nodesert.py) and N2c-like variants: unpooled classes (handoff spec),
class-specific smearing, the PROMPT 6.2 <20-plot pooling rule, leave-one-savanna-plot-out. numpy OLS = statsmodels OLS."""
import sys, json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, V
NB = int(sys.argv[1]); DESERT = sys.argv[2] == "desert"
CL = ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"] + (["Desert"] if DESERT else [])
excl = [11, 13, 15, 17] if DESERT else [11, 13, 15, 16, 17]
d = sites(fill=False); d = d[d.pt.isin(CL)].reset_index(drop=True); d["na"] = (d.continent == "North America").astype(float)
print("n sites", len(d), d.pt.value_counts().to_dict())
G = pd.read_parquet(f"{V}/out/cells_all_codes.parquet")
inc = [f"n{k}" for k in range(1, 18) if k not in excl]; G["n"] = G[inc].sum(axis=1); G = G[G.n >= 20].copy()
G["bio01"] = G.bio01.fillna(G.bio01_fill); G["bio12"] = G.bio12.fillna(G.bio12_fill); G = G.dropna(subset=["bio01", "bio12"]).copy()
G["lnP"] = np.log(G.bio12.clip(lower=1)); G["na"] = (G.continent == "North America").astype(float)
G["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(G.lat)) * G.n / 100.0
def shares(woody):
    m = {"Forest": [1, 2, 3, 4, 5] + ([8] if woody == "Forest" else []), "Shrubland": [6, 7], "Savanna": [9] + ([8] if woody == "Savanna" else []),
         "Grassland": [10], "Agriculture": [12, 14]}
    if DESERT: m["Desert"] = [16]
    return {k: G[[f"n{c}" for c in v]].sum(axis=1).values / G.n.values for k, v in m.items()}
Gz = np.column_stack([np.ones(len(G)), G.bio01, G.lnP, G.na]); area = G.area.values
def est(s, F, pool=None, classsmear=False):
    """pool: dict plot-class -> class used for both the plot dummy and the landscape class."""
    pool = pool or {}
    pt = s.pt.map(lambda k: pool.get(k, k)).values; levels = [k for k in CL if k not in pool]
    y = s.log_rs.values; Z = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na])
    bA = np.linalg.lstsq(Z, y, rcond=None)[0]; tA = (np.exp(Gz @ bA) * np.exp(y - Z @ bA).mean() * area).sum()
    D = np.column_stack([(pt == k).astype(float) for k in levels[1:]]); XC = np.column_stack([Z, D])
    bC = np.linalg.lstsq(XC, y, rcond=None)[0]; rC = y - XC @ bC; smC = np.exp(rC).mean()
    coef = {"Forest": 0.0, **{k: bC[4 + i] for i, k in enumerate(levels[1:])}}
    tC = 0
    for k in CL:   # landscape class k uses the coefficient of the class it is pooled into
        kk = pool.get(k, k)
        sm_k = np.exp(rC[pt == kk]).mean() if classsmear else smC
        tC = tC + F[k] * np.exp(Gz @ bC[:4] + coef[kk]) * sm_k
    tC = (tC * area).sum()
    return tA / tC - 1, coef, tA / 1e15, tC / 1e15
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
deg = 2.0; blk = (np.floor(d.lon / deg).astype(int).astype(str) + "_" + np.floor(d.lat / deg).astype(int).astype(str)).values
ub = np.unique(blk); gi = {b: np.where(blk == b)[0] for b in ub}
R = {"n": len(d), "counts": d.pt.value_counts().to_dict(), "cells": len(G)}
POOLS = {"unpooled (handoff)": None, "Sav->Grass": {"Savanna": "Grassland"}, "Sav->Forest": {"Savanna": "Forest"},
         "Sav+Shrub->Grass": {"Savanna": "Grassland", "Shrubland": "Grassland"}}
if DESERT: POOLS["Sav+Shrub+Des->Grass"] = {"Savanna": "Grassland", "Shrubland": "Grassland", "Desert": "Grassland"}
for xw, woody in [("X1", "Forest"), ("X2", "Savanna")]:
    F = shares(woody)
    R[xw] = {"landscape_share": {k: round(float(np.average(v, weights=area)), 3) for k, v in F.items()}}
    for pname, pool in POOLS.items():
        for cs in [False, True]:
            infl, coef, tA, tC = est(d, F, pool, cs)
            rng = np.random.default_rng(0); bs = []
            for _ in range(NB):
                s = d.iloc[rng.integers(0, len(d), len(d))]
                if pool is None and s.pt.nunique() < len(CL): continue       # handoff skip rule (L78)
                if pool is not None and set(s.pt.map(lambda k: pool.get(k, k))) != set(CL) - set(pool): continue
                bs.append(est(s, F, pool, cs)[0])
            key = f"{pname} | {'class-specific' if cs else 'pooled'} smearing"
            R[xw][key] = dict(infl=round(float(infl), 4), ci_iid=q(bs), n_boot=len(bs), A=round(tA, 2), C=round(tC, 2),
                              coef={k: round(float(v), 3) for k, v in coef.items()})
            print(xw, key, R[xw][key])
    # leave-one-savanna-plot-out (handoff spec)
    sav = np.where(d.pt == "Savanna")[0]
    R[xw]["LOO_savanna"] = [round(float(est(d.drop(index=i).reset_index(drop=True), F)[0]), 4) for i in sav]
    print(xw, "LOO savanna:", R[xw]["LOO_savanna"])
# multi-class coefficients with HC3 (statsmodels, same spec as exp_poststrat.py L66)
m = smf.ols("log_rs ~ bio01 + lnP + C(continent) + C(pt, Treatment(reference='Forest'))", data=d).fit(cov_type="HC3")
R["coef_hc3"] = {k.split("T.")[-1].rstrip("]"): [round(float(m.params[k]), 3), round(float(m.bse[k]), 3)] for k in m.params.index if "pt" in k}
print(R["coef_hc3"])
sv = d[d.pt == "Savanna"]; print("savanna plots:", sv[["lat", "lon", "continent", "country", "ecosystem", "code"]].to_dict("records"))
json.dump(R, open(f"{V}/out/n2cd_{'c' if DESERT else 'd'}.json", "w"), indent=1)
