"""PROXY tests of the attenuation reading of N2b (exp_forest_bias.py): numpy OLS, same spec
log_rs ~ bio01 + lnP + continent + flag. Site climate = nearest original-pipeline site."""
import sys, json, numpy as np, pandas as pd
S, OUT = sys.argv[1:3]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
d["W"] = d.code.isin([1, 2, 3, 4, 5]).astype(float); d["W8"] = d.code.isin([1, 2, 3, 4, 5, 8]).astype(float)
d["X"] = d.plot_forest.astype(float); d["na"] = (d.continent == "North America").astype(float)
y = d.log_rs.values
Z = lambda s: np.column_stack([np.ones(len(s)), s.bio01, s.lnP, s.na])
def ols(Xm, yy): return np.linalg.lstsq(Xm, yy, rcond=None)[0]
def stats(s):
    Zs = Z(s); yy = s.log_rs.values
    bX = ols(np.column_stack([Zs, s.X]), yy)[-1]
    bW = ols(np.column_stack([Zs, s.W]), yy)[-1]
    bW8 = ols(np.column_stack([Zs, s.W8]), yy)[-1]
    both = ols(np.column_stack([Zs, s.X, s.W]), yy)           # surrogacy: W should add nothing given X
    lam = ols(np.column_stack([Zs, s.W]), s.X.values)[-1]      # E[X | W, Z] slope = regression-calibration factor
    lam8 = ols(np.column_stack([Zs, s.W8]), s.X.values)[-1]
    return dict(bX=bX, bW=bW, bW8=bW8, bX_givenW=both[-2], bW_givenX=both[-1], lam=lam, lam8=lam8,
                expected_bW=lam * bX, gap=bW - lam * bX, diffXW=bX - bW)
base = stats(d)
rng = np.random.default_rng(0); B = []
for _ in range(2000):
    B.append(stats(d.iloc[rng.integers(0, len(d), len(d))]))
B = pd.DataFrame(B)
deg = 2.0
blk = (np.floor(d.lon / deg).astype(int).astype(str) + "_" + np.floor(d.lat / deg).astype(int).astype(str)).values
ub = np.unique(blk); gi = {b: np.where(blk == b)[0] for b in ub}
rng = np.random.default_rng(1); BB = []
for _ in range(2000):
    ix = np.concatenate([gi[b] for b in rng.choice(ub, len(ub))]); BB.append(stats(d.iloc[ix]))
BB = pd.DataFrame(BB)
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
R = {"n": len(d), "n_blocks_2deg": len(ub)}
for k in base:
    R[k] = dict(est=round(float(base[k]), 3), iid2000=q(B[k]), block2deg=q(BB[k]))
# Forest plots only: Rs in forest vs non-forest pixels given climate (differential misclassification check)
f = d[d.X == 1]
bfw = ols(np.column_stack([Z(f), f.W]), f.log_rs.values)[-1]
rng = np.random.default_rng(2); bb = []
for _ in range(2000):
    s = f.iloc[rng.integers(0, len(f), len(f))]; bb.append(ols(np.column_stack([Z(s), s.W]), s.log_rs.values)[-1])
R["forest_plots_only_W_coef"] = dict(n=len(f), n_in_forest_pixel=int(f.W.sum()), est=round(float(bfw), 3), iid2000=q(bb))
# multi-class plot effects (exp_poststrat.py mapping) to see which non-forest classes carry the binary effect
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}
pt = d.ecosystem.replace(rep).values; cls = ["Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]
Xm = np.column_stack([Z(d)] + [(pt == k).astype(float) for k in cls]); bm = ols(Xm, y)
res = y - Xm @ bm; XtXi = np.linalg.inv(Xm.T @ Xm); hii = np.einsum("ij,jk,ik->i", Xm, XtXi, Xm)
V = XtXi @ (Xm.T * (res / (1 - hii)) ** 2) @ Xm @ XtXi   # HC3
R["multiclass_vs_forest"] = {k: dict(n=int((pt == k).sum()), coef=round(float(bm[4 + i]), 3), se_hc3=round(float(np.sqrt(V[4 + i, 4 + i])), 3)) for i, k in enumerate(cls)}
json.dump(R, open(OUT, "w"), indent=1); print(json.dumps(R, indent=1))
