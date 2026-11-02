"""Pixel-forest shares at plots in the N2b sample under three IGBP crosswalks, and landscape shares (no climate needed
except for the final WorldClim dropna, which is approximated)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import samp, LC, V, REP_B, cells
d = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
d["plot_forest"] = d.ecosystem.replace(REP_B).eq("Forest").astype(int)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d = d[inbox & d.continent.isin(["Asia", "North America"])].dropna(subset=["log_rs"]).copy()
d["code"] = samp(LC, d.lon.values, d.lat.values); d = d[d.code > 0]
print("N2b sample before WorldClim drop: n =", len(d), " plot forest share", round(d.plot_forest.mean(), 4), " count", int(d.plot_forest.sum()))
f = d[d.plot_forest == 1]
for nm, codes in [("1-5", [1, 2, 3, 4, 5]), ("1-5+8", [1, 2, 3, 4, 5, 8]), ("1-5+8+9", [1, 2, 3, 4, 5, 8, 9])]:
    print(f"  [{nm}] pixel-forest share at plots = {np.isin(d.code, codes).mean():.4f} ({int(np.isin(d.code, codes).sum())}); forest plots in such pixels = {np.isin(f.code, codes).mean():.4f}")
# forest plots in non-forest (1-5) pixels: what are they
nf = f[~np.isin(f.code, [1, 2, 3, 4, 5])]
print("forest plots in non-1-5 pixels:", len(nf), nf.code.astype(int).value_counts().to_dict())
print("  share in IGBP 8/9:", round(np.isin(nf.code, [8, 9]).mean(), 3), " share in water/urban (17/13):", round(np.isin(nf.code, [13, 17]).mean(), 3))
# drop the 4 coastal sites without proxy climate -> 577
for fill in [True, False]:
    g = cells(fill=fill)
    print(f"cells (fill={fill}): n={len(g)}; area-weighted landscape forest share 1-5 = {np.average(g.f, weights=g.veg_area_m2):.4f}; 1-5+8 = {np.average(g.f8, weights=g.veg_area_m2):.4f}; 1-5+8+9 = {np.average(g.f89, weights=g.veg_area_m2):.4f}")
g = pd.read_parquet(f"{V}/out/cells_all_codes.parquet")
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g["n"] = g[inc].sum(axis=1); g = g[g.n >= 20]
w = (np.cos(np.radians(g.lat)) * g.n)
print("cells before any climate drop:", len(g), " forest share 1-5:", round(float((g[[f'n{k}' for k in [1,2,3,4,5]]].sum(1) / g.n * w).sum() / w.sum()), 4),
      " 1-5+8:", round(float((g[[f'n{k}' for k in [1,2,3,4,5,8]]].sum(1) / g.n * w).sum() / w.sum()), 4))
