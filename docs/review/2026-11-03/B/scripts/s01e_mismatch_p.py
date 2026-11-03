"""Re-generate the s01 cases and print the KS p-values of the port and of the literal R re-derivation where they
differ (the 3 's01' mismatches), with n, m and whether the test was exact."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
import s01_cast_compare as S
rng = np.random.default_rng(2026)
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
    gj = kn.nearest_km(s); gij = kn.nearest_km(s, pred)
    d1, p1, kind1 = kn.ks_greater(gj, gij); d2, p2, ex = rcast.r_ks_greater(gj, gij)
    if p1 != p2 and abs(p1 - p2) > 1e-15 * max(p1, p2):
        print(f"case {i}: n={len(s)} m={len(pred)} test={kind1} ties={len(np.unique(np.r_[gj, gij])) < len(gj)+len(gij)} port p={p1:.3e} R-literal p={p2:.3e}")
