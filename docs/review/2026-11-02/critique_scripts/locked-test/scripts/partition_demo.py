"""clean_test.py builds folds from each candidate's own complete rows (L49, L53). Show that losing one site that is alone
in its 5-deg block re-partitions ALL blocks (exact Asia rows, seed 42), whereas losing a site in a shared block does not."""
import sys
import numpy as np, pandas as pd
from sklearn.metrics import adjusted_rand_score
W = sys.argv[1]
a = pd.read_parquet(f"{W}/out/asia_384.parquet").reset_index(drop=True)
def fold_labels(df, seed, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); rng = np.random.default_rng(seed); rng.shuffle(u)
    lab = np.empty(len(df), int)
    for f, vb in enumerate(np.array_split(u, k)): lab[np.isin(b, vb)] = f
    return lab, b
lab0, b = fold_labels(a, 42)
u, c = np.unique(b, return_counts=True); single = set(u[c == 1])
i_single = next(i for i in range(len(a)) if b[i] in single); i_shared = next(i for i in range(len(a)) if b[i] not in single)
for name, i in [("drop site in singleton block", i_single), ("drop site in shared block", i_shared)]:
    keep = np.ones(len(a), bool); keep[i] = False
    lab1, _ = fold_labels(a[keep].reset_index(drop=True), 42)
    print(f"{name}: adjusted Rand index of remaining sites' fold partition vs original = {adjusted_rand_score(lab0[keep], lab1):.3f}")
