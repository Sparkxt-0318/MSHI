"""Retransformation check for N2b/N2d (PROXY climate). Pooled Duan smearing (handoff) vs class-specific smearing
(Duan 1983 / Manning 1998 remedy for group heteroscedasticity) vs a log-link GLM fitted to Rs (no retransformation)."""
import sys, json, numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import levene
S, G, OUT = sys.argv[1:4]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
d["na"] = (d.continent == "North America").astype(float); d["X"] = d.plot_forest.astype(float)
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}
d["pt"] = d.ecosystem.replace(rep)
g0 = pd.read_parquet(G)
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g0["n"] = g0[inc].sum(axis=1); g = g0[g0.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
g["lnP"] = np.log(g.bio12.clip(lower=1)); g["na"] = (g.cont == "North America").astype(float)
g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0); g["f"] = g[["n1", "n2", "n3", "n4", "n5"]].sum(axis=1) / g.n
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na]); area = g.area.values; f = g.f.values
def binary(s):
    y = s.log_rs.values; Z = np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na]); Zc = np.column_stack([Z, s.X])
    bA = np.linalg.lstsq(Z, y, rcond=None)[0]; bC = np.linalg.lstsq(Zc, y, rcond=None)[0]
    rA, rC = y - Z @ bA, y - Zc @ bC; x = s.X.values == 1
    A = (np.exp(Gz @ bA) * np.mean(np.exp(rA)) * area).sum()
    eF, eN = np.exp(Gz @ bC[:4] + bC[4]), np.exp(Gz @ bC[:4])
    Cp = ((f * eF + (1 - f) * eN) * np.mean(np.exp(rC)) * area).sum()
    Cs = ((f * eF * np.mean(np.exp(rC[x])) + (1 - f) * eN * np.mean(np.exp(rC[~x]))) * area).sum()
    # class-specific smearing for A too (A is climate-only: one class) -> unchanged
    return np.array([A / Cp - 1, A / Cs - 1, bC[4], bC[4] + np.log(np.mean(np.exp(rC[x])) / np.mean(np.exp(rC[~x])))])
R = {}
b = binary(d)
y = d.log_rs.values; Zc = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na, d.X]); rC = y - Zc @ np.linalg.lstsq(Zc, y, rcond=None)[0]
R["resid_sd_forest_nonforest"] = [round(float(rC[d.X == 1].std(ddof=1)), 3), round(float(rC[d.X == 0].std(ddof=1)), 3)]
R["brown_forsythe_p"] = float(levene(rC[d.X == 1], rC[d.X == 0], center="median").pvalue)
R["resid_sd_by_class"] = {k: [int((d.pt == k).sum()), round(float(rC[d.pt.values == k].std(ddof=1)), 3)] for k in ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]}
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
rng = np.random.default_rng(0); I = np.array([binary(d.iloc[rng.integers(0, len(d), len(d))]) for _ in range(2000)])
blk = (np.floor(d.lon / 2).astype(int).astype(str) + "_" + np.floor(d.lat / 2).astype(int).astype(str)).values
ub = np.unique(blk); gi = {k: np.where(blk == k)[0] for k in ub}
rng = np.random.default_rng(1); K = np.array([binary(d.iloc[np.concatenate([gi[k] for k in rng.choice(ub, len(ub))])]) for _ in range(2000)])
R["binary_inflation_pooled_smearing"] = dict(est=round(float(b[0]), 4), iid=q(I[:, 0]), block2=q(K[:, 0]))
R["binary_inflation_class_smearing"] = dict(est=round(float(b[1]), 4), iid=q(I[:, 1]), block2=q(K[:, 1]))
R["forest_effect_log_geomean"] = dict(est=round(float(b[2]), 3), iid=q(I[:, 2]))
R["forest_effect_arith_mean_scale(log ratio)"] = dict(est=round(float(b[3]), 3), iid=q(I[:, 3]), block2=q(K[:, 3]))
# log-link GLM on Rs (quasi-Poisson and Gamma): estimates the arithmetic-mean ratio directly
Xg = sm.add_constant(d[["bio01", "lnP", "na", "X"]].astype(float))
for nm, fam in [("quasi_poisson", sm.families.Poisson()), ("gamma_log", sm.families.Gamma(sm.families.links.Log()))]:
    mg = sm.GLM(d.rs.values, Xg, family=fam).fit(cov_type="HC3")
    R[f"glm_{nm}_forest_coef"] = dict(est=round(float(mg.params["X"]), 3), ci=[round(float(v), 3) for v in mg.conf_int().loc["X"]])
    # GLM-based totals: A from GLM without X, C post-stratified
    mA = sm.GLM(d.rs.values, Xg.drop(columns="X"), family=fam).fit()
    tA = (np.exp(Gz @ mA.params.values) * area).sum()
    pC = mg.params.values; tC = ((f * np.exp(Gz @ pC[:4] + pC[4]) + (1 - f) * np.exp(Gz @ pC[:4])) * area).sum()
    R[f"glm_{nm}_inflation"] = round(float(tA / tC - 1), 4)
json.dump(R, open(OUT, "w"), indent=1); print(json.dumps(R, indent=1))
