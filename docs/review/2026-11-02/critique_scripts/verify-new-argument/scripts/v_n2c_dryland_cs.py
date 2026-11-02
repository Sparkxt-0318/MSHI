"""Finding 03 counter-check: does the <20-plot pooling rule necessarily remove the large inflation? Try 'nearest neighbour'
merges that keep the low-Rs dryland classes together (Savanna+Shrubland(+Desert)), which a referee could also call nearest.
N2c needs climate for barren cells, which the atlas lacks: cells filled from the nearest atlas cell (any distance), so N2c
results are approximate; N2d (no desert) uses the 1-deg fill as before."""
import sys, json, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, V
NB = int(sys.argv[1])
clim = pd.read_parquet(f"{V}/out/atlas_clim.parquet"); tree = BallTree(np.radians(clim[["lat", "lon"]].values), metric="haversine")
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
for DESERT in [False, True]:
    CL = ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"] + (["Desert"] if DESERT else [])
    excl = [11, 13, 15, 17] if DESERT else [11, 13, 15, 16, 17]
    d = sites(fill=False); d = d[d.pt.isin(CL)].reset_index(drop=True); d["na"] = (d.continent == "North America").astype(float)
    G = pd.read_parquet(f"{V}/out/cells_all_codes.parquet")
    inc = [f"n{k}" for k in range(1, 18) if k not in excl]; G["n"] = G[inc].sum(axis=1); G = G[G.n >= 20].copy()
    if DESERT:
        m = G.bio01.isna().values; dist, idx = tree.query(np.radians(G.loc[m, ["lat", "lon"]].values), k=1)
        G.loc[m, "bio01"] = clim.bio01.values[idx[:, 0]]; G.loc[m, "bio12"] = clim.bio12.values[idx[:, 0]]
        print("N2c cells:", len(G), "filled from atlas:", int(m.sum()), "median fill distance deg:", round(float(np.median(dist) * 180 / np.pi), 2))
    else:
        G["bio01"] = G.bio01.fillna(G.bio01_fill); G["bio12"] = G.bio12.fillna(G.bio12_fill); G = G.dropna(subset=["bio01", "bio12"]).copy()
    G["lnP"] = np.log(G.bio12.clip(lower=1)); G["na"] = (G.continent == "North America").astype(float)
    area = ((111.32e3 * 0.5) ** 2 * np.cos(np.radians(G.lat)) * G.n / 100.0).values
    Gz = np.column_stack([np.ones(len(G)), G.bio01, G.lnP, G.na])
    def shares(woody):
        mm = {"Forest": [1, 2, 3, 4, 5] + ([8] if woody == "Forest" else []), "Shrubland": [6, 7], "Savanna": [9] + ([8] if woody == "Savanna" else []),
              "Grassland": [10], "Agriculture": [12, 14]}
        if DESERT: mm["Desert"] = [16]
        return {k: G[[f"n{c}" for c in v]].sum(axis=1).values / G.n.values for k, v in mm.items()}
    def est(s, F, pool, cs=True):
        pool = pool or {}; pt = s.pt.map(lambda k: pool.get(k, k)).values; levels = [k for k in CL if k not in pool]
        y = s.log_rs.values; Z = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na])
        bA = np.linalg.lstsq(Z, y, rcond=None)[0]; tA = (np.exp(Gz @ bA) * np.exp(y - Z @ bA).mean() * area).sum()
        XC = np.column_stack([Z] + [(pt == k).astype(float) for k in levels[1:]]); bC = np.linalg.lstsq(XC, y, rcond=None)[0]
        smC = np.exp(y - XC @ bC).mean(); coef = {"Forest": 0.0, **{k: bC[4 + i] for i, k in enumerate(levels[1:])}}
        rC = y - XC @ bC
        tC = sum(F[k] * np.exp(Gz @ bC[:4] + coef[pool.get(k, k)]) * (np.exp(rC[pt == pool.get(k, k)]).mean() if cs else smC) for k in CL)
        return tA / (tC * area).sum() - 1, coef
    pools = {"unpooled (handoff)": None, "Sav->Shrub (19 plots, still <20)": {"Savanna": "Shrubland"},
             "Sav+Shrub->Agri": {"Savanna": "Agriculture", "Shrubland": "Agriculture"}}
    if DESERT:
        pools["dryland: Sav+Des->Shrub (32 plots)"] = {"Savanna": "Shrubland", "Desert": "Shrubland"}
        pools["Sav+Shrub+Des->Grass"] = {"Savanna": "Grassland", "Shrubland": "Grassland", "Desert": "Grassland"}
    print("==== N2c (with desert)" if DESERT else "==== N2d (no desert)", "n =", len(d), d.pt.value_counts().to_dict())
    for xw, woody in [("X1", "Forest"), ("X2", "Savanna")]:
        F = shares(woody)
        for pname, pool in pools.items():
            infl, coef = est(d, F, pool); rng = np.random.default_rng(0); bs = []
            for _ in range(NB):
                s = d.iloc[rng.integers(0, len(d), len(d))]
                need = set(CL) - set(pool or {})
                if set(s.pt.map(lambda k: (pool or {}).get(k, k))) != need: continue
                bs.append(est(s, F, pool)[0])
            print(f"  {xw} {pname:38s} infl {infl:.4f} iid {q(bs)} (n_boot {len(bs)}) coef { {k: round(float(v), 3) for k, v in coef.items()} }")
