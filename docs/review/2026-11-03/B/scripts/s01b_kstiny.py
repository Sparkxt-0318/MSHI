import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
rng = np.random.default_rng(5)
for n, m, shift in [(57, 800, 3.0), (50, 120, 3.0), (155, 800, 2.0), (30, 40, 0.5), (300, 4000, 0.3)]:
    x = rng.gamma(2, 10, n); y = rng.gamma(2, 10, m) * (1 + shift)
    d1, p1, kind = kn.ks_greater(x, y)
    d2, p2, ex = rcast.r_ks_greater(x, y)
    print(n, m, kind, ex, d1, d2, p1, p2)
