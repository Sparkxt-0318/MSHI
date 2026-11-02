import sys, warnings, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
warnings.filterwarnings("ignore")
W=sys.argv[1]; SRDB=sys.argv[2]
def clus(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
s = pd.read_csv(SRDB, low_memory=False)
R0 = pd.read_parquet(f"{W}/data/records_v3.parquet"); R0 = R0[~R0.f_offland & ~R0.f_coord].copy()
QC = ~(R0.f_method | R0.f_quality | R0.f_coverage | R0.f_ecosys | R0.f_dup)
# ---- N3 subcategories (srdb only, QC)
r = R0[QC & R0.src.eq("srdb")].copy(); r["row"] = r.rec_id.str.replace("srdb_", "").astype(int)
for c in ["Study_number", "Meas_method", "Ecosystem_type"]: r[c+"_"] = s.loc[r.row, c].values
r = r.reset_index(drop=True); r["site"] = clus(r)
cats = {}
for sid, g in r.groupby("site"):
    if len(g) < 2: continue
    v = g[["log_rs", "Study_number_", "Study_midyear", "Meas_method_", "Ecosystem_type_"]].values
    for i in range(len(v)):
        for j in range(i+1, len(v)):
            if v[i,1] != v[j,1] and v[i,2]==v[j,2] and v[i,3]==v[j,3] and v[i,4]==v[j,4]:
                cats.setdefault("diff_study_same_year_same_method_same_eco", []).append(sid)
            if v[i,1] != v[j,1] and v[i,2]==v[j,2]:
                cats.setdefault("diff_study_same_year", []).append(sid)
for k, v in cats.items():
    c = pd.Series(v).value_counts()
    print(f"N3 {k}: pairs {c.sum()}, from {len(c)} sites; top-1 site share {c.iloc[0]/c.sum():.3f}, top-3 {c.head(3).sum()/c.sum():.3f}")
# ---- E1 same-year vs diff-year (QC, srdb+cosore as in E1)
q = R0[QC].reset_index(drop=True); q["site"] = clus(q)
multi = q[q.groupby("site").log_rs.transform("size") >= 2]
yr = multi.dropna(subset=["Study_midyear"])
P = []
for sid, g in yr.groupby("site"):
    v = g[["log_rs", "Study_midyear"]].values
    for i in range(len(v)):
        for j in range(i+1, len(v)):
            P.append((sid, 0.5*(v[i,0]-v[j,0])**2, v[i,1]==v[j,1]))
P = pd.DataFrame(P, columns=["site","h","same"])
print("E1 pair-weighted same-year", round(P[P.same].h.mean(),4), "diff-year", round(P[~P.same].h.mean(),4), "n", P.same.sum(), (~P.same).sum())
for lab, sub in [("same_year", P[P.same]), ("diff_year", P[~P.same])]:
    c = sub.groupby("site").size().sort_values(ascending=False)
    print(f"  {lab}: from {len(c)} sites; top-5 share {c.head(5).sum()/c.sum():.3f}; site-weighted mean {sub.groupby('site').h.mean().mean():.4f}")
rng = np.random.default_rng(0); sites = P.site.unique(); gi = {k: np.where(P.site.values==k)[0] for k in sites}
bt = []
for _ in range(1000):
    idx = np.concatenate([gi[k] for k in rng.choice(sites, len(sites))]); hh, sm = P.h.values[idx], P.same.values[idx]
    bt.append(hh[~sm].mean() - hh[sm].mean())
print("  cluster-bootstrap CI (diff-year minus same-year):", np.quantile(bt,[.025,.975]).round(4))
# implied share: what fraction of within-site variance is 'same-year'? E1 says 'mostly plot-to-plot'
print("  ratio same/diff-year semivariance:", round(P[P.same].h.mean()/P[~P.same].h.mean(),3))
