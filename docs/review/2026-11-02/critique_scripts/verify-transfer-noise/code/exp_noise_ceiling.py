"""Exploratory E1: noise ceiling for site-level Rs prediction from within-site replicate records (SRDB v5 + COSORE).
Variance components of log Rs (one-way random effects, unbalanced; ANOVA estimator), per continent and filter set.
Ceiling for predicting a single record: ICC1 = s2b/(s2b+s2w). Ceiling for a site mean of n records:
rel_i = s2b/(s2b + s2w/n_i); expected ceiling R2 over a test set = mean signal variance / mean total variance.
Also splits within-site variance into same-year (plot-to-plot) and between-year components.
"""
import json, sys
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree

REC, OUT = sys.argv[1], sys.argv[2]
r = pd.read_parquet(REC)
r = r[~r.f_offland & ~r.f_coord].copy()
QC = ~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)


def cluster(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]


def varcomp(df):
    g = df.groupby("site").log_rs; n = g.size(); k = len(n); N = n.sum()
    if k < 5: return None
    m = g.mean(); grand = df.log_rs.mean()
    ssb = (n * (m - grand) ** 2).sum(); ssw = ((df.log_rs - df.site.map(m)) ** 2).sum()
    msb, msw = ssb / (k - 1), ssw / (N - k); n0 = (N - (n ** 2).sum() / N) / (k - 1)
    s2b = max((msb - msw) / n0, 0); s2w = msw
    return dict(sites=int(k), records=int(N), s2_between=float(s2b), s2_within=float(s2w),
                sd_within_log=float(np.sqrt(s2w)), icc_single_record=float(s2b / (s2b + s2w)))


R = {}
for tag, rr in [("qc", r[QC]), ("repo", r)]:
    rr = rr.reset_index(drop=True).assign(site=lambda x: cluster(x))
    multi = rr[rr.groupby("site").log_rs.transform("size") >= 2]
    R[tag] = {"all": varcomp(multi)}
    for cont, sub in multi.groupby("continent"):
        R[tag][cont] = varcomp(sub)
    # ceiling for the actual site-mean target (all sites, incl. singletons)
    vc = R[tag]["all"]; n_i = rr.groupby("site").size()
    sig = vc["s2_between"]; noise = vc["s2_within"] / n_i
    R[tag]["ceiling_r2_site_mean_target"] = float(sig / (sig + noise.mean()))
    R[tag]["ceiling_r2_single_record_target"] = vc["icc_single_record"]
    # same-year vs different-year pairs within site
    yr = multi.dropna(subset=["Study_midyear"])
    same, diff = [], []
    for _, gsite in yr.groupby("site"):
        v = gsite[["log_rs", "Study_midyear"]].values
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                (same if v[i, 1] == v[j, 1] else diff).append(0.5 * (v[i, 0] - v[j, 0]) ** 2)
    R[tag]["half_sq_diff_same_year"] = dict(n_pairs=len(same), mean=float(np.mean(same)) if same else None)
    R[tag]["half_sq_diff_diff_year"] = dict(n_pairs=len(diff), mean=float(np.mean(diff)) if diff else None)
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps(R, indent=1))
