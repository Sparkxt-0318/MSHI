"""Case 'exactly k clusters of n/k sites' (q = k, every cluster has n/k sites): the port and the literal re-derivation
with R's rep() semantics (rep(integer(0), Inf) = integer(0); assigning to an empty selection is a no-op) give the same
split, i.e. CAST does not stop there."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
rng = np.random.default_rng(1)
pred = np.c_[rng.uniform(0, 30, 500), rng.uniform(35, 60, 500)]
for nk_len, reps in [(1, 2), (100, 2), (100, 3)]:
    cen = np.array([[2, 40], [8, 45], [14, 50], [20, 55], [26, 59]], float)
    s = np.repeat(cen, reps, axis=0) + rng.normal(0, 0.01, (5 * reps, 2))
    f, info = kn.knndm_folds(s, pred, 5, 0.5, "hierarchical", 0, nk_len=nk_len)
    r = rcast.knndm_geo(s, pred, 5, 0.5, nk_len, rand=kn.random_folds(len(s), 5, 0) + 1)
    print(f"n={len(s)} nk_len={nk_len}: port q={info['q']} sizes={info['fold_sizes']} | R-semantics q={r['q']} "
          f"same partition={rcast.same_partition(f, r['clust'])}")
