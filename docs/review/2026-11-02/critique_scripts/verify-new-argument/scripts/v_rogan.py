"""Finding 10: Rogan-Gladen what-if — correct each cell's IGBP-1-5 fraction with the plot-level confusion rates."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, cells
d = sites(fill=False); g = cells(fill=True)
d["na"] = (d.continent == "North America").astype(float); g["na"] = (g.continent == "North America").astype(float)
se = d.pixel_forest[d.plot_forest == 1].mean(); fpr = d.pixel_forest[d.plot_forest == 0].mean()
g["f_rg"] = ((g.f - fpr) / (se - fpr)).clip(0, 1)
print(f"Se={se:.3f} FPR={fpr:.3f}; landscape f: raw {np.average(g.f, weights=g.veg_area_m2):.3f} -> RG {np.average(g.f_rg, weights=g.veg_area_m2):.3f}")
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); area = g.veg_area_m2.values
y = d.log_rs.values; Z = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na]); X = d.plot_forest.values
bA = np.linalg.lstsq(Z, y, rcond=None)[0]; bC = np.linalg.lstsq(np.column_stack([Z, X]), y, rcond=None)[0]
smA = np.exp(y - Z @ bA).mean(); smC = np.exp(y - np.column_stack([Z, X]) @ bC).mean()
A = (np.exp(Gz @ bA) * smA * area).sum()
for col in ["f", "f_rg"]:
    f = g[col].values; C = ((f * np.exp(Gz @ bC[:4] + bC[4]) + (1 - f) * np.exp(Gz @ bC[:4])) * smC * area).sum()
    print(col, "inflation A/C-1 =", round(A / C - 1, 4))
