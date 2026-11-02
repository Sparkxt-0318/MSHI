"""PROXY re-run of exp_poststrat.py / exp_poststrat_nodesert.py (N2c/N2d) with numpy OLS (same spec as the statsmodels formulas).
Site climate = nearest original-pipeline site; cell-centre climate = legacy atlas (89-90% of footprint area)."""
import sys, json, numpy as np, pandas as pd
S, G, OUT = sys.argv[1:4]
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}
d0 = pd.read_parquet(S); d0["pt"] = d0.ecosystem.replace(rep)
g0 = pd.read_parquet(G)
CW = {1: "Forest", 2: "Forest", 3: "Forest", 4: "Forest", 5: "Forest", 6: "Shrubland", 7: "Shrubland", 9: "Savanna",
      10: "Grassland", 12: "Agriculture", 14: "Agriculture", 16: "Desert"}

def grid(woody, CL):
    m = dict(CW); m[8] = woody
    if "Desert" not in CL: m.pop(16)
    g = g0.copy()
    for k in CL: g[k] = g[[f"n{c}" for c, kk in m.items() if kk == k]].sum(axis=1)
    g["n"] = g[CL].sum(axis=1); g = g[g.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
    for k in CL: g[k] = g[k] / g.n
    g["lnP"] = np.log(g.bio12.clip(lower=1)); g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * g.n / 100.0
    g["na"] = (g.cont == "North America").astype(float)
    return g

def est(s, g, CL):
    pt = s.pt.values
    cls = [k for k in CL if k != "Forest" and k in set(pt)]
    Xa = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, (s.continent == "North America").astype(float)])
    Xc = np.column_stack([Xa] + [(pt == k).astype(float) for k in cls])
    y = s.log_rs.values
    ba = np.linalg.lstsq(Xa, y, rcond=None)[0]; bc = np.linalg.lstsq(Xc, y, rcond=None)[0]
    smA = np.mean(np.exp(y - Xa @ ba)); smC = np.mean(np.exp(y - Xc @ bc))
    Ga = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na])
    base = Ga @ bc[:4]
    tA = (np.exp(Ga @ ba) * smA * g.area).sum()
    tC = 0.0; contrib = {}
    for k in CL:                      # exp_poststrat.py L69-71: classes present in both landscape and sample
        if k not in set(pt): continue
        eff = 0.0 if k == "Forest" else bc[4 + cls.index(k)]
        v = (g[k].values * np.exp(base + eff) * smC * g.area).sum(); tC += v; contrib[k] = v / 1e15
    coefs = {k: float(bc[4 + i]) for i, k in enumerate(cls)}
    return tA / 1e15, tC / 1e15, coefs, contrib

R = {}
for tag, CL in [("N2c", ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]),
                ("N2d", ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"])]:
    d = d0[d0.pt.isin(CL)].dropna(subset=["log_rs", "bio01", "lnP"]).copy()
    for name, woody in [("X1", "Forest"), ("X2", "Savanna")]:
        g = grid(woody, CL)
        tA, tC, coefs, contrib = est(d, g, CL)
        rng = np.random.default_rng(0); bs = []; skipped = 0
        for _ in range(1000):
            s = d.iloc[rng.integers(0, len(d), len(d))]
            if s.pt.nunique() < len(CL): skipped += 1; continue
            a, c, _, _ = est(s, g, CL); bs.append(a / c - 1)
        out = dict(n_sites=len(d), landscape_share={k: round(float(np.average(g[k], weights=g.area)), 3) for k in CL},
                   A=round(tA, 2), C=round(tC, 2), inflation=round(tA / tC - 1, 3),
                   iid1000_ci=[round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)], skipped=skipped,
                   class_coefs_vs_forest={k: round(v, 3) for k, v in coefs.items()},
                   plot_counts=d.pt.value_counts().to_dict())
        # leave-one-savanna-plot-out
        sav = np.where(d.pt.values == "Savanna")[0]
        loo = []
        for i in sav:
            s = d.drop(d.index[i]); a, c, cf, _ = est(s, g, CL); loo.append((round(a / c - 1, 3), round(cf["Savanna"], 3)))
        out["leave_one_savanna_out(inflation,coef)"] = loo
        # pool small classes (<20 plots) into a neighbour, as the Phase-3 plan requires
        for pname, pool in [("savanna->forest", {"Savanna": "Forest"}), ("savanna->grassland", {"Savanna": "Grassland"}),
                            ("savanna+shrub->grassland", {"Savanna": "Grassland", "Shrubland": "Grassland"})]:
            CLp = [k for k in CL if k not in pool]
            def est_pool(s, g=g, CL=CL, pool=pool, CLp=CLp):
                s = s.assign(pt=s.pt.replace(pool)); gg = g.copy()
                for src, dst in pool.items(): gg[dst] = gg[dst] + gg[src]
                return est(s, gg, CLp)
            a, c, cf, _ = est_pool(d)
            out[f"pooled[{pname}]"] = round(a / c - 1, 3)
        R[f"{tag}_{name}"] = out
        print(tag, name, json.dumps(out))
json.dump(R, open(OUT, "w"), indent=1)
