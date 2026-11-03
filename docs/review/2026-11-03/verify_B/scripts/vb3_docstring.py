"""B-3 independent checks (R is not installed; R semantics are emulated from the R sources read as data).
(1) CAST's random split, sample(rep(1:k, ceiling(n/k)), size = n, replace = FALSE): Monte Carlo (numpy permutation of
    the label multiset, first n kept) of the share of draws with an empty fold, for k = 5 and 10, n = k+2 .. (k-1)^2+5,
    compared with the condition ceiling(n/k) <= k*ceiling(n/k) - n (all copies of one label undrawn).
(2) Edge case 'exactly k clusters of n/k sites': 20 sites in 5 tight equal clusters, k = 5, nk_len = 1 (grid {5});
    the port's split, and CAST's merge line emulated step by step with R semantics:
      clust_i <- setdiff(1:k, unique(clust_k))           -> integer(0)
      rep(clust_i, ceiling(nk/length(clust_i)))           -> rep(integer(0), Inf) = integer(0) (do_rep: lx == 0 returns
                                                             before 'times' is checked; seq.c lines 698-706)
      [1:sum(is.na(clust_k))]                             -> integer(0)[c(1, 0)] = NA (length 1)
      clust_k[is.na(clust_k)] <- NA                       -> empty selection: no-op
    so CAST keeps the big clusters' folds and evaluates the split like the port."""
import math
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
from mshi.analysis import knndm as kn

rng = np.random.default_rng(7)
for k in (5, 10):
    rows = []
    for n in range(k + 2, (k - 1) ** 2 + 6):
        c = math.ceil(n / k)
        labels = np.repeat(np.arange(k), c)
        draws = 20000 if k == 5 else 4000
        empty = 0
        for _ in range(draws):
            drawn = rng.permutation(labels)[:n]
            empty += len(np.unique(drawn)) < k
        cond = c <= k * c - n
        rows.append((n, empty / draws, cond))
    mism = [(n, p, c) for n, p, c in rows if (p > 0) != c]
    print(f"k={k}: n with an empty fold observed: {[n for n, p, _ in rows if p > 0]}")
    print(f"      n <= (k-1)^2 = {(k-1)**2} with NO empty fold observed: {[n for n, p, _ in rows if p == 0 and n <= (k-1)**2]}")
    print(f"      mismatches with the condition ceiling(n/k) <= k*ceiling(n/k) - n: {mism}")
    print(f"      largest observed share: {max(p for _, p, _ in rows):.4f}")

# (2) edge case
cen = np.array([[2, 40], [9, 44], [15, 49], [21, 54], [27, 58]], float)
sites = np.repeat(cen, 4, axis=0) + rng.normal(0, 0.02, (20, 2))
pred = np.c_[rng.uniform(0, 30, 800), rng.uniform(35, 60, 800)]
folds, info = kn.knndm_folds(sites, pred, 5, 0.5, "hierarchical", 0, nk_len=1)
print(f"\n(2) port: random_cv={info['random_cv']} q={info['q']} fold sizes={info['fold_sizes']} W={info['W']:.2f}")
# CAST's steps with R semantics (emulated)
n, k, nk = 20, 5, 5
Z = kn.scipy_linkage(kn.squareform(kn.pairwise_km(sites), checks=False), method="ward")
lab = kn.cut_tree_labels(Z, n, [nk])[nk]
size = np.bincount(lab)
centre, v = kn._pc1(sites)
order = np.argsort(kn.cluster_scores(sites, lab, centre, v), kind="stable")
clust_k = {int(c): None for c in order}
ci = 1
for c in order:                                   # "We don't merge big clusters"
    if size[c] >= n / k:
        clust_k[int(c)] = ci
        ci += 1
clust_i = [f for f in range(1, k + 1) if f not in set(clust_k.values())]        # setdiff -> integer(0)
times = math.ceil(nk / len(clust_i)) if clust_i else math.inf                   # nk/0 = Inf in R
rep = [] if len(clust_i) == 0 else clust_i * times                              # do_rep: lx == 0 -> integer(0)
n_na = sum(v is None for v in clust_k.values())                                 # 0
idx = [1, 0] if n_na == 0 else list(range(1, n_na + 1))                         # R 1:0 = c(1, 0)
value = [rep[i - 1] if i - 1 < len(rep) else None for i in idx if i != 0]       # x[c(1,0)] on length 0 -> NA
targets = [c for c, f in clust_k.items() if f is None]                          # empty selection -> no-op
for t, val in zip(targets, value):
    clust_k[t] = val
cast = np.array([clust_k[int(c)] for c in lab]) - 1
same = len(set(zip(cast.tolist(), folds.tolist()))) == len(np.unique(cast)) == len(np.unique(folds))
print(f"    CAST (R semantics): clust_i={clust_i}, times={times}, rep={rep}, value after [1:0]={value} (NA), "
      f"targets={targets}; fold sizes {np.bincount(cast).tolist()}; same partition as the port: {same}")
