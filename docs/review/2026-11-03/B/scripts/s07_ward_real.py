"""R hclust ward.D2 (naive Lance-Williams on squared great-circle distances, vectorised) vs scipy 'ward' on the real
analysis QC site coordinates of Asia, Europe and North America: merge heights, and R cutree partitions for every q
of the kNNDM grid (k=5, nk_len=100). Also checks for NaN/negative squared heights (non-Euclidean input)."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np, pandas as pd
from scipy.cluster.hierarchy import linkage
from mshi.analysis import knndm as kn
import rcast

def naive_ward_d2_fast(D):
    n = len(D)
    S = D.astype(float) ** 2
    np.fill_diagonal(S, np.inf)
    size = np.ones(n)
    alive = np.ones(n, bool)
    label = np.array([-(i + 1) for i in range(n)])
    merge, height, minS = [], [], np.inf
    for step in range(1, n):
        Sm = np.where(alive[:, None] & alive[None, :], S, np.inf)
        flat = int(np.argmin(Sm))
        i, j = divmod(flat, n)
        if i > j:
            i, j = j, i
        d = S[i, j]
        minS = min(minS, d)
        merge.append((label[i], label[j])); height.append(np.sqrt(d) if d >= 0 else np.nan)
        k = np.flatnonzero(alive); k = k[(k != i) & (k != j)]
        ni, nj, nk = size[i], size[j], size[k]
        v = ((ni + nk) * S[i, k] + (nj + nk) * S[j, k] - nk * S[i, j]) / (ni + nj + nk)
        S[i, k] = v; S[k, i] = v
        size[i] += size[j]; alive[j] = False; S[j, :] = np.inf; S[:, j] = np.inf
        label[i] = step
    return np.array(merge), np.array(height), minS

d = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet").sort_values("site_id")
for c in ["Asia", "Europe", "North America"]:
    x = d.loc[d.continent_geo == c, ["lon", "lat"]].to_numpy(float)
    n = len(x)
    D = kn.pairwise_km(x, 6371.0)
    Z = linkage(D[np.triu_indices(n, 1)], method="ward")
    m_naive, h_naive, minS = naive_ward_d2_fast(D)
    grid = kn.q_grid(5, n, 100)
    cuts = kn.cut_tree_labels(Z, n, grid)
    bad = [int(q) for q in grid if not np.array_equal(rcast.r_cutree(m_naive, int(q)) - 1, cuts[int(q)])]
    print(f"{c}: n={n} heights equal (rtol 1e-9)={np.allclose(h_naive, Z[:,2], rtol=1e-9)} "
          f"NaN heights scipy={int(np.isnan(Z[:,2]).sum())} naive={int(np.isnan(h_naive).sum())} "
          f"monotone={bool(np.all(np.diff(Z[:,2]) >= 0))} cut mismatches over {len(grid)} grid q: {bad}")
