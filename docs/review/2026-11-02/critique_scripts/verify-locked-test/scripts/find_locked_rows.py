"""Identify which Asia/Europe QC sites were dropped in the locked test (n 384/235) by matching
rmse_rs_intercept = 386.9086311104987 exactly; also search exhaustively for alternative drop sets."""
import sys, json, itertools
import numpy as np, pandas as pd
st = pd.read_parquet(sys.argv[1])
A = st[st.continent == "Asia"].reset_index(drop=True); E = st[st.continent == "Europe"].reset_index(drop=True)
print("Asia", len(A), "Europe", len(E))
TARGET = 386.9086311104987
def rmse_int(a_logrs, e_logrs):
    return float(np.sqrt(np.mean((np.exp(np.full(len(e_logrs), a_logrs.mean())) - np.exp(e_logrs)) ** 2)))
# 1) the prior reviewer's claimed drops
a_drop = ["v3qc_00184", "v3qc_00576", "v3qc_00604"]; e_drop = ["v3qc_00559"]
a = A[~A.site_id.isin(a_drop)]; e = E[~E.site_id.isin(e_drop)]
v = rmse_int(a.log_rs.values, e.log_rs.values)
print("claimed drops ->", len(a), len(e), repr(v), "diff", v - TARGET)
# 2) exhaustive: for each Europe drop j, solve for Asia mean c giving TARGET, then 3-sum search over Asia drops
ya = A.log_rs.values; ye = E.log_rs.values; tot = ya.sum()
hits = []
for j in range(len(E)):
    ro = np.exp(np.delete(ye, j)); n = len(ro)
    # mean((x - ro)^2) = T^2  -> x^2 - 2 x mean(ro) + mean(ro^2) - T^2 = 0
    b = ro.mean(); cc = (ro ** 2).mean() - TARGET ** 2
    disc = b * b - cc
    if disc < 0: continue
    for x in (b - np.sqrt(disc), b + np.sqrt(disc)):
        if x <= 0: continue
        c = np.log(x); need = tot - 384 * c   # sum of the 3 dropped Asia log_rs
        # 3-sum: for pairs (i<k), need third value ya[m] = need - ya[i] - ya[k], m > k
        order = np.argsort(ya); ys = ya[order]
        for i in range(len(ys)):
            for k in range(i + 1, len(ys)):
                t = need - ys[i] - ys[k]
                if t < ys[k] - 1e-9: break
                m = np.searchsorted(ys, t - 1e-7)
                while m < len(ys) and ys[m] <= t + 1e-7:
                    if m > k:
                        drop = sorted([order[i], order[k], order[m]])
                        vv = rmse_int(np.delete(ya, drop), np.delete(ye, j))
                        hits.append((abs(vv - TARGET), j, tuple(drop), vv))
                    m += 1
hits = sorted(set(hits))
print("n candidate drop sets within 1e-7 on the 3-sum:", len(hits))
for h in hits[:10]:
    print("absdiff %.3e" % h[0], "EU drop", E.site_id[h[1]], E.country[h[1]], "Asia drops", list(A.site_id[list(h[2])]), list(A.country[list(h[2])]), repr(h[3]))
