"""Finding 03 counter-check: crude empirical-Bayes (method-of-moments) partial pooling of the N2d class effects (PROMPT 6.3
item 6 asks for partial pooling) -> what happens to the X1/X2 inflation? Climate + continent coefficients re-fitted with the
shrunk class offsets held fixed. PROXY climate, N2d spec, pooled Duan smearing as in the handoff."""
import sys, numpy as np, pandas as pd, statsmodels.formula.api as smf
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, V
CL = ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"]
d = sites(fill=False); d = d[d.pt.isin(CL)].reset_index(drop=True); d["na"] = (d.continent == "North America").astype(float)
m = smf.ols("log_rs ~ bio01 + lnP + C(continent) + C(pt, Treatment(reference='Forest'))", data=d).fit(cov_type="HC3")
est = {"Forest": 0.0}; se = {"Forest": 0.0}
for k in CL[1:]:
    nm = f"C(pt, Treatment(reference='Forest'))[T.{k}]"; est[k] = m.params[nm]; se[k] = m.bse[nm]
e = np.array([est[k] for k in CL]); s2 = np.array([se[k] ** 2 for k in CL])
mu = e.mean(); tau2 = max(e.var(ddof=1) - s2.mean(), 0)
shr = {k: mu + tau2 / (tau2 + se[k] ** 2) * (est[k] - mu) if k != "Forest" else 0.0 for k in CL}
# re-reference so that Forest is 0 (forest is estimated precisely, keep it unshrunk as reference)
print("tau2", round(tau2, 4), "raw", {k: round(v, 3) for k, v in est.items()}, "shrunk", {k: round(v, 3) for k, v in shr.items()})
G = pd.read_parquet(f"{V}/out/cells_all_codes.parquet")
inc = [f"n{k}" for k in range(1, 18) if k not in (11, 13, 15, 16, 17)]; G["n"] = G[inc].sum(axis=1); G = G[G.n >= 20].copy()
G["bio01"] = G.bio01.fillna(G.bio01_fill); G["bio12"] = G.bio12.fillna(G.bio12_fill); G = G.dropna(subset=["bio01", "bio12"]).copy()
G["lnP"] = np.log(G.bio12.clip(lower=1)); G["na"] = (G.continent == "North America").astype(float)
area = ((111.32e3 * 0.5) ** 2 * np.cos(np.radians(G.lat)) * G.n / 100.0).values; Gz = np.column_stack([np.ones(len(G)), G.bio01, G.lnP, G.na])
y = d.log_rs.values; Z = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na])
bA = np.linalg.lstsq(Z, y, rcond=None)[0]; tA = (np.exp(Gz @ bA) * np.exp(y - Z @ bA).mean() * area).sum()
for lab, coef in [("unpooled", est), ("partially pooled (EB)", shr)]:
    off = d.pt.map(coef).values; b = np.linalg.lstsq(Z, y - off, rcond=None)[0]; sm = np.exp(y - off - Z @ b).mean()
    for xw, woody in [("X1", "Forest"), ("X2", "Savanna")]:
        mm = {"Forest": [1, 2, 3, 4, 5] + ([8] if woody == "Forest" else []), "Shrubland": [6, 7], "Savanna": [9] + ([8] if woody == "Savanna" else []), "Grassland": [10], "Agriculture": [12, 14]}
        tC = sum(G[[f"n{c}" for c in v]].sum(axis=1).values / G.n.values * np.exp(Gz @ b + coef[k]) for k, v in mm.items()) * sm
        print(f"  {lab:24s} {xw} inflation {tA / (tC * area).sum() - 1:.4f}")
