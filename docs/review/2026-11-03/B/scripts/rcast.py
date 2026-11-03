"""Independent, literal re-derivation of CAST 1.2.0 knndm_geo (R semantics), written for the review from
R_knndm.R, R's ks.test.R / ks.c, R's hclust/cutree semantics and twosamples::wass_stat. It shares no code with
mshi.analysis.knndm (only scipy's linkage is reused for the hierarchy, since R cannot be run here; a naive
ward.D2 (Lance-Williams on squared dissimilarities, as R's hclust.f iOpt=8) is provided to check that too).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.cluster.hierarchy import linkage


# ----------------------------------------------------------------- distances (own haversine, brute force)
def gc_matrix(a, b, R):
    a = np.radians(np.asarray(a, float))
    b = np.radians(np.asarray(b, float))
    lon1, lat1 = a[:, 0][:, None], a[:, 1][:, None]
    lon2, lat2 = b[:, 0][None, :], b[:, 1][None, :]
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


# ----------------------------------------------------------------- R ks.test(x, y, alternative="greater")
def r_ks_greater(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    nx, ny = float(len(x)), len(y)
    exact = nx * ny < 10000
    w = np.concatenate([x, y])
    order = np.argsort(w, kind="stable") + 1          # R order(): stable
    z = np.cumsum(np.where(order <= nx, 1 / nx, -1 / ny))
    ties = len(np.unique(w)) < (nx + ny)
    if ties:
        sw = np.sort(w, kind="stable")
        z = z[np.r_[np.flatnonzero(np.diff(sw) != 0), int(nx + ny) - 1]]
    stat = z.max()
    # psmirnov(..., lower.tail = FALSE)
    if stat <= 0:
        return stat, 1.0, exact
    if stat > 1:
        return stat, 0.0, exact
    if not exact:
        n = nx * ny / (nx + ny)
        ret = -math.expm1(-2 * n * stat ** 2)
        return stat, 1 - ret, exact
    # exact: C psmirnov_exact (upper tail, one-sided)
    m, nn = int(nx), int(ny)
    md, nd = float(m), float(nn)
    q = (0.5 + math.floor(stat * md * nd - 1e-7)) / (md * nd)
    zz = None
    if ties:
        dd = (np.diff(np.sort(w, kind="stable")) != 0)
        if dd.any():
            zz = np.r_[0, dd.astype(int), 1]

    def test(r, s):
        return (r - s) >= q
    u = [0.0] * (nn + 1)
    for j in range(1, nn + 1):
        u[j] = 1.0 if (test(0.0, j / nd) and (zz is None or zz[j])) else u[j - 1]
    for i in range(1, m + 1):
        if test(i / md, 0.0) and (zz is None or zz[i]):
            u[0] = 1.0
        for j in range(1, nn + 1):
            if test(i / md, j / nd) and (zz is None or zz[i + j]):
                u[j] = 1.0
            else:
                v = i / (i + j)
                ww = j / (i + j)
                u[j] = v * u[j] + ww * u[j - 1]
    return stat, u[nn], exact


# ----------------------------------------------------------------- twosamples::wass_stat (power 1)
def wass_stat(a, b):
    a = np.sort(np.asarray(a, float))
    b = np.sort(np.asarray(b, float))
    joint = np.sort(np.concatenate([a, b]))
    fa = np.searchsorted(a, joint[:-1], side="right") / len(a)
    fb = np.searchsorted(b, joint[:-1], side="right") / len(b)
    return float(np.sum(np.abs(fa - fb) * np.diff(joint)))


# ----------------------------------------------------------------- hierarchy -> R merge matrix, R cutree (C code)
def scipy_to_r_merge(Z, n):
    """R hclust merge matrix from a scipy linkage (rows in the same order): singletons -(i+1), clusters by row."""
    merge = np.zeros((n - 1, 2), dtype=int)
    for r in range(n - 1):
        for c in range(2):
            v = int(Z[r, c])
            merge[r, c] = -(v + 1) if v < n else (v - n + 1)
    return merge


def naive_ward_d2(D):
    """R hclust(method = "ward.D2") by the naive algorithm (Lance-Williams on squared dissimilarities): merge matrix
    in R format and heights. Smallest pair; ties broken by the first (i, j) in row-major order of the upper
    triangle (R's hclust.f uses its NN list; ties may differ from both)."""
    n = len(D)
    S = D.astype(float) ** 2
    active = list(range(n))
    size = {i: 1 for i in range(n)}
    label = {i: -(i + 1) for i in range(n)}       # R label of the cluster represented by index i
    merge, height = [], []
    S = S.copy()
    for step in range(1, n):
        best = None
        for ai, i in enumerate(active):
            for j in active[ai + 1:]:
                if best is None or S[i, j] < best[0]:
                    best = (S[i, j], i, j)
        d, i, j = best
        merge.append((label[i], label[j]))
        height.append(math.sqrt(d))
        for k in active:
            if k in (i, j):
                continue
            ni, nj, nk = size[i], size[j], size[k]
            v = ((ni + nk) * S[i, k] + (nj + nk) * S[j, k] - nk * S[i, j]) / (ni + nj + nk)
            S[i, k] = S[k, i] = v
        size[i] += size[j]
        active.remove(j)
        label[i] = step
    m = np.array(merge)
    # R puts the singleton (negative) first, and orders two singletons/two clusters by value
    for r in range(len(m)):
        a, b = m[r]
        if a < 0 and b < 0:
            m[r] = sorted((a, b), reverse=True)    # -1 before -2 in R (abs ascending)
        elif a > 0 and b > 0:
            m[r] = sorted((a, b))
        elif a > 0 > b:
            m[r] = (b, a)
    return m, np.array(height)


def r_cutree(merge, k):
    """Literal port of R's C cutree for one k."""
    n = len(merge) + 1
    sing = [True] * n
    m_nr = [0] * n
    z = [0] * n
    ans = [0] * n
    for kk in range(1, n):
        m1, m2 = int(merge[kk - 1, 0]), int(merge[kk - 1, 1])
        if m1 < 0 and m2 < 0:
            m_nr[-m1 - 1] = m_nr[-m2 - 1] = kk
            sing[-m1 - 1] = sing[-m2 - 1] = False
        elif m1 < 0 or m2 < 0:
            if m1 < 0:
                j, m1 = -m1, m2
            else:
                j = -m2
            for l in range(n):
                if m_nr[l] == m1:
                    m_nr[l] = kk
            m_nr[j - 1] = kk
            sing[j - 1] = False
        else:
            for l in range(n):
                if m_nr[l] == m1 or m_nr[l] == m2:
                    m_nr[l] = kk
        if k == n - kk:
            z = [0] * n
            nclust = 0
            for l in range(n):
                if sing[l]:
                    nclust += 1
                    ans[l] = nclust
                else:
                    if z[m_nr[l] - 1] == 0:
                        nclust += 1
                        z[m_nr[l] - 1] = nclust
                    ans[l] = z[m_nr[l] - 1]
            return np.array(ans)
    if k == n:
        return np.arange(1, n + 1)
    raise ValueError(k)


# ----------------------------------------------------------------- R seq / round
def r_clustgrid(k, n, nk_len):
    frm, to = math.log(k), math.log(n - 2)
    if nk_len > 2:
        if frm == to:
            s = [frm] * nk_len
        else:
            n1 = nk_len - 1
            s = [frm] + [frm + i * ((to - frm) / n1) for i in range(1, n1)] + [to]
    else:
        s = [frm, to][:nk_len]
    nk = [int(np.rint(math.exp(v))) for v in s]
    out = []
    for v in nk:
        if v not in out:
            out.append(v)
    return out


# ----------------------------------------------------------------- knndm_geo
def cv_distances(distmat_na, clust):
    n = len(clust)
    out = np.full(n, np.nan)
    seen = []
    for f in clust:
        if f not in seen:
            seen.append(f)
    for f in seen:
        te = np.flatnonzero(np.asarray(clust) == f)
        tr = np.setdiff1d(np.arange(n), te)
        out[te] = [np.nanmin(distmat_na[tr, j]) for j in te]
    return out


def knndm_geo(tcoords, predcoords, k, maxp, nk_len=100, R=6371.0, hclust="scipy", pc_sign=+1,
              rand=None, return_grid=False):
    tcoords = np.asarray(tcoords, float)
    n = len(tcoords)
    distmat = gc_matrix(tcoords, tcoords, R)
    dna = distmat.copy()
    np.fill_diagonal(dna, np.nan)
    Gj = np.nanmin(dna, axis=1)
    Gij = gc_matrix(predcoords, tcoords, R).min(axis=1)
    stat, p, exact = r_ks_greater(Gj, Gij)
    res = {"ks_D": stat, "ks_p": p, "ks_exact": exact, "Gj": Gj, "Gij": Gij}
    if p >= 0.05:
        clust = np.asarray(rand)
        res.update(random=True, clust=clust, Gjstar=cv_distances(dna, clust))
        res["W"] = wass_stat(res["Gjstar"], Gij)
        return res
    iu = np.triu_indices(n, 1)
    if hclust == "scipy":
        Z = linkage(distmat[iu], method="ward")
        merge = scipy_to_r_merge(Z, n)
    else:
        merge, _h = naive_ward_d2(distmat)
    grid = r_clustgrid(k, n, nk_len)
    # prcomp(tcoords, center=TRUE, scale.=FALSE, rank=1)
    center = tcoords.mean(axis=0)
    _u, _s, vt = np.linalg.svd(tcoords - center, full_matrices=False)
    rot = vt[0] * pc_sign
    W = {}
    groups = {}
    for nk in grid:
        clust_nk = r_cutree(merge, nk)
        levels = np.sort(np.unique(clust_nk))                      # table(): factor levels in numeric order
        freq = np.array([np.sum(clust_nk == lv) for lv in levels])
        centr = np.array([(tcoords[clust_nk == lv].mean(axis=0) - center) @ rot for lv in levels])
        o = np.argsort(centr, kind="stable")                       # order(): stable
        lv_o, fr_o = levels[o], freq[o]
        clust_k = [None] * len(lv_o)
        ci = 1
        for i in range(len(lv_o)):
            if fr_o[i] >= n / k:
                clust_k[i] = ci
                ci += 1
        used = {c for c in clust_k if c is not None}
        rest = [c for c in range(1, k + 1) if c not in used]
        nas = [i for i in range(len(lv_o)) if clust_k[i] is None]
        if nas:
            if not rest:
                raise RuntimeError("R: rep(integer(0), Inf) -> error")
            rep = rest * math.ceil(nk / len(rest))
            for t, i in enumerate(nas):
                clust_k[i] = rep[t]
        mapping = dict(zip(lv_o.tolist(), clust_k))
        ck = np.array([mapping[v] for v in clust_nk])
        tab = np.array([np.sum(ck == v) for v in np.unique(ck)]) / n
        if not np.any(tab > maxp):
            gs = cv_distances(dna, ck)
            W[nk] = wass_stat(gs, Gij)
            groups[nk] = ck
    if not W:
        raise RuntimeError("no valid configuration")
    vals = [W.get(nk, np.nan) for nk in grid]
    kf = grid[int(np.nanargmin(vals))]                             # which.min: first minimum
    res.update(random=False, q=kf, W=W[kf], clust=groups[kf], Gjstar=cv_distances(dna, groups[kf]),
               grid=grid, Wgrid=W)
    return res


def same_partition(a, b):
    a, b = np.asarray(a), np.asarray(b)
    pairs = set(zip(a.tolist(), b.tolist()))
    return len(pairs) == len(np.unique(a)) == len(np.unique(b))
