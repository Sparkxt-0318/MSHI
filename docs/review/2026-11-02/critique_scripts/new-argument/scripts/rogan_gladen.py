"""If the IGBP product's misclassification at the plots (sens = P(pixel forest | plot forest), fpr = P(pixel forest | plot non-forest))
also applied to the landscape (the attenuation reading's premise), the implied true forest fraction per cell is (f - fpr)/(sens - fpr).
PROXY totals, N2b spec with pooled smearing (as handoff)."""
import sys, json, numpy as np, pandas as pd
S, G = sys.argv[1:3]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
d["na"] = (d.continent == "North America").astype(float)
g0 = pd.read_parquet(G); inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g0["n"] = g0[inc].sum(axis=1); g = g0[g0.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
g["lnP"] = np.log(g.bio12.clip(lower=1)); g["na"] = (g.cont == "North America").astype(float)
g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0)
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); area = g.area.values
y = d.log_rs.values; Z = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na]); Zc = np.column_stack([Z, d.plot_forest])
bA = np.linalg.lstsq(Z, y, rcond=None)[0]; bC = np.linalg.lstsq(Zc, y, rcond=None)[0]
smA, smC = np.mean(np.exp(y - Z @ bA)), np.mean(np.exp(y - Zc @ bC))
A = (np.exp(Gz @ bA) * smA * area).sum()
for nm, codes in [("1-5", [1, 2, 3, 4, 5]), ("1-5+8", [1, 2, 3, 4, 5, 8])]:
    W = d.code.isin(codes); X = d.plot_forest == 1
    sens, fpr = W[X].mean(), W[~X].mean()
    f = g[[f"n{c}" for c in codes]].sum(axis=1).values / g.n.values
    fc = np.clip((f - fpr) / (sens - fpr), 0, 1)
    for lab, ff in [("as used (product f)", f), ("Rogan-Gladen corrected f", fc)]:
        C = ((ff * np.exp(Gz @ bC[:4] + bC[4]) + (1 - ff) * np.exp(Gz @ bC[:4])) * smC * area).sum()
        print(f"crosswalk {nm:6s} sens={sens:.3f} fpr={fpr:.3f} | {lab:26s} landscape forest share={np.average(ff, weights=area):.3f}  inflation A/C-1={A / C - 1:.4f}")
