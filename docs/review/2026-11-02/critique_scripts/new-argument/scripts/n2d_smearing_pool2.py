"""N2d (no desert) PROXY: pooled vs class-specific smearing, with iid bootstrap; plus pooled small classes."""
import sys, json, numpy as np, pandas as pd
import statsmodels.api as sm
S, G, OUT = sys.argv[1:4]
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}
CL = ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"]
d = pd.read_parquet(S); d["pt"] = d.ecosystem.replace(rep)
d = d[d.pt.isin(CL)].dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
g0 = pd.read_parquet(G)
CW = {1: "Forest", 2: "Forest", 3: "Forest", 4: "Forest", 5: "Forest", 6: "Shrubland", 7: "Shrubland", 9: "Savanna", 10: "Grassland", 12: "Agriculture", 14: "Agriculture"}
def grid(woody):
    m = dict(CW); m[8] = woody; g = g0.copy()
    for k in CL: g[k] = g[[f"n{c}" for c, kk in m.items() if kk == k]].sum(axis=1)
    g["n"] = g[CL].sum(axis=1); g = g[g.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
    for k in CL: g[k] = g[k] / g.n
    g["lnP"] = np.log(g.bio12.clip(lower=1)); g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * g.n / 100.0
    g["na"] = (g.cont == "North America").astype(float); return g
def est(s, g, CLx, smear):
    pt = s.pt.values; cls = [k for k in CLx if k != "Forest"]
    Xa = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, (s.continent == "North America").astype(float)])
    Xc = np.column_stack([Xa] + [(pt == k).astype(float) for k in cls]); y = s.log_rs.values
    ba = np.linalg.lstsq(Xa, y, rcond=None)[0]; bc = np.linalg.lstsq(Xc, y, rcond=None)[0]; rc = y - Xc @ bc
    Ga = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); base = Ga @ bc[:4]
    tA = (np.exp(Ga @ ba) * np.mean(np.exp(y - Xa @ ba)) * g.area).sum(); tC = 0.0
    for k in CLx:
        eff = 0.0 if k == "Forest" else bc[4 + cls.index(k)]
        smk = np.mean(np.exp(rc)) if smear == "pooled" else np.mean(np.exp(rc[pt == k]))
        tC += (g[k].values * np.exp(base + eff) * smk * g.area).sum()
    return tA / tC - 1
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
R = {}
for name, woody in [("X1", "Forest"), ("X2", "Savanna")]:
    g = grid(woody)
    for pname, pool in [("savanna+shrub->grassland", {"Savanna": "Grassland", "Shrubland": "Grassland"}), ("savanna->forest,shrub->grassland", {"Savanna": "Forest", "Shrubland": "Grassland"})]:
        dd = d.assign(pt=d.pt.replace(pool)); gg = g.copy()
        for a, b in pool.items(): gg[b] = gg[b] + gg[a]
        CLx = [k for k in CL if k not in pool]
        for smear in ["pooled", "class"]:
            e = est(dd, gg, CLx, smear)
            rng = np.random.default_rng(0); bs = []
            for _ in range(500):
                s = dd.iloc[rng.integers(0, len(dd), len(dd))]
                if s.pt.nunique() < len(CLx): continue
                bs.append(est(s, gg, CLx, smear))
            R[f"{name}|{pname}|{smear}_smearing"] = dict(inflation=round(float(e), 3), iid_ci=q(bs), n_boot=len(bs))
            print(name, pname, smear, R[f"{name}|{pname}|{smear}_smearing"])
json.dump(R, open(OUT, "w"), indent=1)
