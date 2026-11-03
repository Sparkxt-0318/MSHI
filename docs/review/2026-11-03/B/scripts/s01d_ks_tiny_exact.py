"""The 3 's01' KS mismatches: exact-test cases with p ~ 1e-31 vs 0. Recompute such cases: port vs literal R recursion vs
scipy's exact one-sided p (no ties), to confirm the differences are only at negligible magnitudes."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from scipy import stats
from mshi.analysis import knndm as kn
rng = np.random.default_rng(0)
worst = 0.0
for i in range(300):
    n, m = int(rng.integers(20, 90)), int(rng.integers(20, 110))
    if n * m >= 10000:
        continue
    shift = rng.uniform(0, 4)
    x = rng.gamma(2, 10, n); y = rng.gamma(2, 10, m) * (1 + shift)
    d1, p1, _ = kn.ks_greater(x, y); d2, p2, _ = rcast.r_ks_greater(x, y)
    p3 = stats.ks_2samp(x, y, alternative="greater", method="exact").pvalue
    if max(p1, p2, p3) > 1e-12:
        worst = max(worst, abs(p1 - p2) / max(p2, 1e-300), abs(p1 - p3) / max(p3, 1e-300))
    elif p1 != p2:
        print(f"tiny: n={n} m={m} port={p1:.3e} R-literal={p2:.3e} scipy={p3:.3e}")
print("max relative difference among cases with p > 1e-12:", worst)
