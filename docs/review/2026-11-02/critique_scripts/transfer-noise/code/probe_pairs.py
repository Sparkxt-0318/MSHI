import sys, warnings, json, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
warnings.filterwarnings("ignore")
W=sys.argv[1]; SRDB=sys.argv[2]
r = pd.read_parquet(f"{W}/data/records_v3.parquet")
r = r[(r.src == "srdb") & ~r.f_offland & ~r.f_coord].copy()
s = pd.read_csv(SRDB, low_memory=False)
r["row"] = r.rec_id.str.replace("srdb_", "").astype(int)
for c in ["Study_number", "Study_midyear", "Meas_method", "Ecosystem_type"]:
    r[c] = s.loc[r.row, c].values
rr = r[~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)].reset_index(drop=True)
X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
rr["site"] = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
P = []
for sid, g in rr.groupby("site"):
    if len(g) < 2: continue
    v = g[["log_rs", "Study_number", "Study_midyear", "Meas_method", "Ecosystem_type"]].values
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            P.append((sid, 0.5 * (v[i, 0] - v[j, 0]) ** 2, v[i, 1] == v[j, 1], v[i, 2] == v[j, 2], v[i,4]==v[j,4]))
P = pd.DataFrame(P, columns=["site", "h", "same_study", "same_year", "same_eco"])
print("pairs", len(P), "same_study", P.same_study.sum(), "diff_study", (~P.same_study).sum())
# pair-weighted (as N3)
pw = P.groupby("same_study").h.mean(); print("pair-weighted semivar same/diff:", round(pw[True],4), round(pw[False],4))
# top-site concentration of each pair type
for lab, sub in [("same_study", P[P.same_study]), ("diff_study", P[~P.same_study])]:
    c = sub.groupby("site").size().sort_values(ascending=False)
    print(f"{lab}: sites contributing {len(c)}; share of pairs from top 5 sites {c.head(5).sum()/c.sum():.3f}, top 10 {c.head(10).sum()/c.sum():.3f}")
# site-weighted: mean of per-site means
def site_w(sub): return sub.groupby("site").h.mean().mean()
print("site-weighted semivar same/diff:", round(site_w(P[P.same_study]),4), round(site_w(P[~P.same_study]),4))
# sites having both kinds: within-site contrast
both = P.groupby("site").same_study.agg(lambda x: x.any() and (~x).any()); bs = both[both].index
Q = P[P.site.isin(bs)]
per = Q.groupby(["site", "same_study"]).h.mean().unstack()
print("sites with both pair types:", len(bs), "; site-weighted same", round(per[True].mean(),4), "diff", round(per[False].mean(),4),
      "; median ratio diff/same", round((per[False]/per[True]).median(),2), "; frac sites diff>same", round((per[False]>per[True]).mean(),3))
# CI: pair bootstrap (as N3) vs site-cluster bootstrap for the pair-weighted means and the diff-same contrast
rng = np.random.default_rng(0)
sites = P.site.unique(); gidx = {k: np.where(P.site.values == k)[0] for k in sites}
h = P.h.values; ss = P.same_study.values
bt = []
for _ in range(1000):
    pick = rng.choice(sites, len(sites)); idx = np.concatenate([gidx[k] for k in pick])
    hh, s2 = h[idx], ss[idx]; bt.append((hh[s2].mean(), hh[~s2].mean()))
bt = np.array(bt)
print("cluster-bootstrap 95% CI same:", np.quantile(bt[:,0],[.025,.975]).round(4), "diff:", np.quantile(bt[:,1],[.025,.975]).round(4),
      "diff-same:", np.quantile(bt[:,1]-bt[:,0],[.025,.975]).round(4))
print("N3 pair-bootstrap CI same [0.069, 0.0772], diff [0.1307, 0.1406] (widths 0.008, 0.010)")
# E1 same-year vs diff-year using SRDB-only QC (E1 uses srdb+cosore; cosore has no year, so identical pairs)
py = P.dropna(subset=["same_year"])
yy = pd.read_parquet(f"{W}/data/records_v3.parquet")
# same_year False when either year is NaN in N3 code; E1 drops NaN years first -> recompute with years
