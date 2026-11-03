"""Edge cases of knndm_folds: duplicate coordinates (tied merge heights), exactly k clusters of n/k sites (CAST stops,
the port uses the split), n = k + 2 (smallest allowed), and the re-derivation's answer where it exists."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, rcast
from mshi.analysis import knndm as kn
rng = np.random.default_rng(1)
pred = np.c_[rng.uniform(0, 30, 500), rng.uniform(35, 60, 500)]
# (a) duplicates: 4 locations x 5 copies, k = 5
s = np.repeat(np.array([[5, 40], [20, 42], [10, 55], [25, 58]], float), 5, axis=0)
f, info = kn.knndm_folds(s, pred, 5, 0.5, "hierarchical", 0)
r = rcast.knndm_geo(s, pred, 5, 0.5, 100, rand=kn.random_folds(20, 5, 0) + 1, hclust="naive")
print("(a) duplicates: port q", info["q"], "sizes", info["fold_sizes"], "W", round(info["W"], 2),
      "| naive-R q", r.get("q"), "W", round(r["W"], 2), "same partition", rcast.same_partition(f, r["clust"]))
# (b) exactly k clusters of n/k sites: 5 tight pairs, k = 5, nk_len = 1 (grid = [5])
s = np.repeat(np.array([[2, 40], [8, 45], [14, 50], [20, 55], [26, 59]], float), 2, axis=0) + rng.normal(0, 0.01, (10, 2))
f, info = kn.knndm_folds(s, pred, 5, 0.5, "hierarchical", 0, nk_len=1)
try:
    rcast.knndm_geo(s, pred, 5, 0.5, 1, rand=kn.random_folds(10, 5, 0) + 1); rr = "ran"
except RuntimeError as e:
    rr = str(e)
print("(b) k clusters of n/k: port q", info["q"], "sizes", info["fold_sizes"], "| R:", rr)
# (c) n = k + 2
s = np.c_[rng.uniform(0, 30, 7), rng.uniform(35, 60, 7)]
f, info = kn.knndm_folds(np.r_[s[:3] + 0.01, s], pred, 5, 0.5, "hierarchical", 0) if False else (None, None)
s = np.r_[np.array([[1, 40], [1.01, 40], [15, 50], [15.01, 50.01], [28, 58], [28.02, 58]]), np.array([[10, 45]])]
try:
    f, info = kn.knndm_folds(s, pred, 5, 0.5, "hierarchical", 0); print("(c) n = k+2:", info["q"], info["fold_sizes"], info["random_cv"])
except Exception as e:
    print("(c) n = k+2:", type(e).__name__, e)
try:
    kn.knndm_folds(s[:6], pred, 5, 0.5, "hierarchical", 0)
except ValueError as e:
    print("(c') n = k+1:", e)
