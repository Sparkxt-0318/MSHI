"""Trace the exact-test difference on one tie case: the D+ numerator used by the port vs the statistic of the R-literal
re-derivation, and the p-value each gives; then the same recursion with the port's integer test but R's z-vector."""
import sys, math
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
import s01_cast_compare as S
rng = np.random.default_rng(2026)
cases = {}
for i in range(60):
    kind = ["clustered", "dominant", "random", "line", "two_scale"][i % 5]
    n = int(rng.integers(8, 160)); k = int(rng.integers(2, 11))
    if n < k + 2: n = k + 2
    maxp = float(rng.choice([1.0 / k + 0.02, 0.3, 0.5, 0.75, 0.95]))
    if not 1.0 / k < maxp < 1.0: maxp = 0.5 if 1.0 / k < 0.5 else min(0.95, 1.0 / k + 0.1)
    nk_len = int(rng.choice([1, 2, 3, 10, 100]))
    pred = S.sphere_box(rng, int(rng.choice([50, 120, 800])), lon=(-10, 40), lat=(30, 65))
    if kind == "clustered": s = S.clustered(rng, n, max(2, n // 15), 0.2)
    elif kind == "dominant":
        mm = int(0.7 * n); s = np.r_[np.array([15.0, 47.0]) + rng.normal(0, 0.2, (mm, 2)), S.sphere_box(rng, n - mm)]
    elif kind == "random": s = pred[rng.choice(len(pred), min(n, len(pred)), replace=False)]
    elif kind == "line": s = np.c_[np.linspace(0, 30, n) + rng.normal(0, 0.01, n), 45 + rng.normal(0, 0.3, n)]
    else: s = np.r_[S.clustered(rng, n // 2, 3, 0.05), S.sphere_box(rng, n - n // 2)]
    cases[i] = (s, pred)
s, pred = cases[30]
x = kn.nearest_km(s); y = kn.nearest_km(s, pred)
m, n = len(x), len(y)
w = np.concatenate([x, y]); o = np.argsort(w, kind="stable"); is_x = o < m
num = np.cumsum(is_x) * n - np.cumsum(~is_x) * m
check = np.r_[np.diff(w[o]) != 0, True]
print("port d_num:", int(num[check].max()), " max over all positions:", int(num.max()), " m*n:", m * n)
stat, p_r, ex = rcast.r_ks_greater(x, y)
print("R-literal stat*m*n:", stat * m * n, " p:", p_r, " port p:", kn.ks_greater(x, y)[1])
print("all-x-first path reaches D+ =", m * n, "-> the extreme path; m, n =", m, n)
# the extreme value: D+ = 1 means all x below all y; P = 1/choose(m+n, m) under no ties
print("1/choose(m+n, m) =", 1 / math.comb(m + n, m))
