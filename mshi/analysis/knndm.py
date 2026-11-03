"""kNNDM cross-validation folds for sites given in longitude/latitude (Phase 2, item 2: the within-continent
benchmark, next to 5-degree block CV).

k-fold nearest neighbour distance matching (kNNDM; Linnenbrink et al. 2024, Geosci. Model Dev. 17:5897,
doi:10.5194/gmd-17-5897-2024) chooses a k-fold split of the training sites whose cross-validation distances
``Gjstar`` (from each held-out site to the nearest site in the other folds) are distributed like the
prediction distances ``Gij`` (from each prediction location to the nearest training site). The CV error of such
a split estimates the error of a map over the prediction domain, not the error near the training sites.

Source. No maintained Python implementation exists (PyPI has no knndm/pyknndm; spatial-kfold 0.0.4 and spacv
0.0.22 do not implement kNNDM). The paper's publisher and CRAN are blocked here, so the paper itself was not
read. ``knndm_folds`` ports ``knndm_geo`` (geographical space) of the authors' R implementation: CAST 1.2.0
``R/knndm.R`` (by C. Milà and J. Linnenbrink; GitHub HannaMeyer/CAST, branch master, read on 2026-11-03;
SHA-256 in ``CAST_KNNDM_SHA256``; the commit could not be resolved, the GitHub API being blocked). The R
functions it relies on were read from their sources too: ``stats::ks.test`` and ``psmirnov`` (R-devel 4.7.0,
``src/library/stats/R/ks.test.R`` and ``src/ks.c``; R 4.1 ``ks.test.R``; the R NEWS entries for 4.2.0 and 4.4.0)
and ``twosamples::wass_stat`` (twosamples 2.0.1, ``src/stat_functions.cpp``). None of that code was run.

Algorithm (CAST's, for lon/lat coordinates):
1. ``Gij``: great-circle distance from each prediction point to the nearest site; ``Gj``: from each site to the
   nearest other site (leave-one-out).
2. One-sided two-sample Kolmogorov-Smirnov test, R ``ks.test(Gj, Gij, alternative = "greater")``: are the
   ``Gj`` stochastically smaller than the ``Gij``, i.e. are the sites more clustered than the prediction
   locations? If p >= ``ks_alpha`` (0.05 in CAST), a random k-fold split is returned (CAST's fallback).
3. Otherwise: hierarchical clustering (R ``hclust``, ``ward.D2``) of the sites' great-circle distance matrix.
   For each q of ``round(exp(seq(log(k), log(n - 2), length.out = nk_len)))`` (duplicates dropped; small q
   sampled more densely), cut the tree into q clusters; order the clusters by the first principal component of
   the site coordinates evaluated at the cluster centroids (lon/lat degrees); a cluster with at least n/k
   sites becomes a fold of its own, and the other clusters are dealt, in that order, cyclically to the
   remaining folds; a split whose largest fold holds more than ``maxp`` of the sites is skipped; for the others
   compute ``Gjstar`` and W, the integral over distance of |ECDF(Gjstar) - ECDF(Gij)| (``wass_stat`` of the
   twosamples package with power 1: the 1-Wasserstein distance between the two samples). The split with the
   smallest W is returned (the smallest q among exact ties, as R's ``which.min``).
``info["W_random"]`` is W for the random split of the same seed: the reference kNNDM should improve on.

Port notes: the places where the R code leaves a choice open, and every difference from CAST.
- Distances: haversine on a sphere of radius ``earth_radius_km`` (pass ``site_build.earth_radius_km``), in km;
  nearest neighbours from sklearn's ``BallTree(metric="haversine")``. CAST uses ``sf::st_distance``: by default
  (s2) the great-circle distance on a 6371.01-km sphere, in metres; with ``sf_use_s2(FALSE)``, WGS84 ellipsoidal
  geodesics. A constant factor changes no test, clustering or choice, only the unit of W (km here, m in CAST).
  Spherical distances are within -0.45% to +0.56% of WGS84 geodesics (1-3,000 km, measured with pyproj); in nine
  toy configurations (Asia-, Europe-like and boreal boxes, clustered sites) WGS84 distances gave the same q and
  the same split, with W within 1%.
- KS p-value as in R >= 4.4: exact (permutation distribution of D+ given the observed ties, R's ``psmirnov``
  recursion) if n·m < 10000, otherwise exp(-2 D+^2 nm/(n + m)). R before 4.2 used the asymptotic value for
  every one-sided two-sample test; the two differ only when n·m < 10000 (toy cases, not 0.5-degree domains).
- Clustering: scipy ``linkage(method="ward")`` on the condensed distance matrix is R's ``ward.D2`` (the
  Lance-Williams update on squared dissimilarities; the method is reducible for any dissimilarity, so scipy's
  nearest-neighbour chain gives R's hierarchy); merges at exactly tied heights may be ordered differently.
  ``cutree`` is re-implemented: clusters numbered in order of first appearance in the data, as R does; this
  order breaks ties between equal centroid scores (R's ``order`` is stable).
- The sign of the first principal component is arbitrary in R (LAPACK); here the larger loading is made
  positive (closed-form 2 x 2 eigenvector, no LAPACK call). The partition does not depend on the sign unless
  two centroids have exactly equal scores; only the fold labels do.
- Centroids are arithmetic means of lon/lat degrees, as in CAST, so a cluster that spans the antimeridian gets
  a misplaced centroid; this can only change the order in which clusters are dealt to folds.
- Random split: CAST draws n labels without replacement from ``rep(1:k, ceiling(n/k))`` with R's generator, so
  fold sizes can differ by more than one and, for n <= (k - 1)^2, a fold can be empty. Here a balanced random
  permutation from ``numpy.random.default_rng(seed)`` (sizes floor(n/k) or ceil(n/k)). R's draw cannot be
  reproduced in Python either way.
- Fold ids are CAST's cluster labels (its ``clusters`` element) minus one.
- Edge cases: exactly k clusters of n/k sites and no smaller one: CAST stops (``rep`` over an empty set of
  folds), here the split is used. No grid value satisfies ``maxp``: CAST fails without a clear message, here
  RuntimeError. n < k + 2 (the grid would contain q < k): CAST runs, here ValueError.
- Not ported: feature space (``dist_space = "feature"``), k-means (CAST refuses it for lon/lat), train/test
  splits (``test_prop``), sampling prediction points from a ``modeldomain`` polygon, plots.

Inputs, assumptions and limits. Coordinates are (lon, lat) in degrees. The prediction domain is whatever
``pred_lonlat`` holds: how the points are drawn (for example from a lon/lat grid, whose cells shrink with
cos(latitude), uniformly or area-weighted) changes Gij and so the split. W values are comparable only between
splits of the same sites against the same prediction points (``fold_match`` scores any split, e.g. 5-degree
blocks). kNNDM folds can be unbalanced: CAST advises pooling all out-of-fold predictions before computing a
metric (``global_validation``). CAST's KS test treats the leave-one-out distances as independent, but mutual
nearest neighbours share theirs (about a third of the values are duplicates for random sites), so it rejects
more often than its nominal level: with 150 sites drawn at random from the prediction domain's distribution it
rejected in 14% of 400 toy draws (0.5% with the duplicates removed). kNNDM then returns a near-random split (q
close to n; W at most 1.5 times the random split's in 100 toy draws), so the effect is small. Kept as CAST has
it. Results depend on the order of the rows (cluster numbering, random split); memory is O(n^2) for the site
distance matrix. Deterministic for given inputs: the kNNDM split does not use the seed; the seed sets only the
random split (the fallback and ``W_random``). Nothing here reads or writes files.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.cluster.hierarchy import linkage as scipy_linkage
from scipy.spatial.distance import squareform
from sklearn.metrics import DistanceMetric
from sklearn.neighbors import BallTree

CAST_VERSION = "1.2.0"
CAST_KNNDM_SHA256 = "14fded58a7068a74dc4bf86b591b1dc9fa54aa888a68e2b98665459931c8db17"
SOURCE = f"CAST {CAST_VERSION} knndm.R sha256 {CAST_KNNDM_SHA256}"

# R hclust method -> scipy linkage method (the same Lance-Williams updates; R's "ward.D2" is scipy's "ward")
LINKAGES = {"ward.D2": "ward", "single": "single", "complete": "complete", "average": "average",
            "mcquitty": "weighted"}

# R ks.test(): exact p-value when n.x * n.y < 10000 (part of R's definition of the test, not a parameter)
R_KS_EXACT_BELOW = 10000


# ---------------------------------------------------------------- distances

def _lonlat(a, name: str) -> np.ndarray:
    x = np.asarray(a, dtype=float)
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError(f"{name} must have shape (n, 2): lon, lat in degrees; got {x.shape}")
    if not np.isfinite(x).all():
        raise ValueError(f"{name} contains missing or infinite coordinates")
    if (np.abs(x[:, 1]) > 90.0).any():
        raise ValueError(f"{name} has latitudes outside [-90, 90] (columns must be lon, lat)")
    return x


def _latlon_rad(x: np.ndarray) -> np.ndarray:
    """(lat, lon) in radians, the column order of sklearn's haversine metric."""
    return np.radians(x[:, ::-1])


def haversine_km(lon1, lat1, lon2, lat2, earth_radius_km: float = 6371.0) -> np.ndarray:
    """Great-circle distance (km) on a sphere of radius ``earth_radius_km`` between points in degrees
    (numpy broadcasting)."""
    p1, p2 = np.radians(np.asarray(lat1, float)), np.radians(np.asarray(lat2, float))
    dlon = np.radians(np.asarray(lon2, float) - np.asarray(lon1, float))
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2.0 * earth_radius_km * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def pairwise_km(lonlat, earth_radius_km: float = 6371.0) -> np.ndarray:
    """Great-circle distances (km) between all rows of ``lonlat``: symmetric, zero diagonal."""
    x = _lonlat(lonlat, "lonlat")
    d = np.triu(DistanceMetric.get_metric("haversine").pairwise(_latlon_rad(x)) * earth_radius_km, 1)
    return d + d.T


def nearest_km(ref_lonlat, query_lonlat=None, earth_radius_km: float = 6371.0) -> np.ndarray:
    """Distance (km) from each query point to the nearest point of ``ref_lonlat`` (``Gij``). Without
    ``query_lonlat``: from each reference point to the nearest *other* one (leave-one-out, ``Gj``; 0 for a
    duplicated location)."""
    ref = _lonlat(ref_lonlat, "ref_lonlat")
    tree = BallTree(_latlon_rad(ref), metric="haversine")
    if query_lonlat is None:
        if len(ref) < 2:
            raise ValueError("leave-one-out distances need at least two points")
        return tree.query(_latlon_rad(ref), k=2)[0][:, 1] * earth_radius_km
    q = _lonlat(query_lonlat, "query_lonlat")
    return tree.query(_latlon_rad(q), k=1)[0][:, 0] * earth_radius_km


def cv_distances_km(dist: np.ndarray, folds) -> np.ndarray:
    """``Gjstar`` (CAST ``.cv_distances``): for each site, the distance to the nearest site in another fold,
    from the full site-to-site distance matrix ``dist``."""
    f = np.asarray(folds)
    vals = np.unique(f)
    if len(vals) < 2:
        raise ValueError("CV distances need at least two folds")
    out = np.empty(len(f))
    for v in vals:
        te = f == v
        out[te] = dist[np.ix_(te, ~te)].min(axis=1)
    return out


# ---------------------------------------------------------------- the two statistics

def wasserstein_stat(a, b) -> float:
    """``twosamples::wass_stat(a, b)`` with its default power 1: the integral over the pooled sample of
    |ECDF_a - ECDF_b| (the 1-Wasserstein distance; twosamples 2.0.1 ``wass_stat_presort``)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    joint = np.concatenate([a, b])
    o = np.argsort(joint, kind="stable")
    is_a = o < len(a)
    gap = np.abs(np.cumsum(is_a)[:-1] / len(a) - np.cumsum(~is_a)[:-1] / len(b))
    return float(np.sum(gap * np.diff(joint[o])))


def _smirnov_greater_upper(d_num: int, m: int, n: int, check: np.ndarray | None) -> float:
    """P(D+ >= d_num / (m n)) under H0, for samples of sizes m (x) and n (y): R's ``psmirnov_exact_uniq_upper``
    / ``psmirnov_exact_ties_upper`` (one-sided), the probability that a random lattice path from (0, 0) to
    (m, n) reaches i n - j m >= d_num at a point where the pooled sample changes value (``check[i + j - 1]``;
    every point without ties). Integer comparisons replace R's 0.5/(mn) tolerance on the same boundary."""
    def hit(i: int, j: int) -> bool:
        return i * n - j * m >= d_num and (check is None or bool(check[i + j - 1]))

    u = [0.0] * (n + 1)
    for j in range(1, n + 1):
        u[j] = 1.0 if hit(0, j) else u[j - 1]
    for i in range(1, m + 1):
        if hit(i, 0):
            u[0] = 1.0
        for j in range(1, n + 1):
            if hit(i, j):
                u[j] = 1.0
            else:
                u[j] = (i / (i + j)) * u[j] + (j / (i + j)) * u[j - 1]
    return u[n]


def ks_greater(x, y) -> tuple[float, float, str]:
    """R ``ks.test(x, y, alternative = "greater")``, two-sample: D+ = max(ECDF_x - ECDF_y) over the points where
    the pooled sample changes value, and its p-value (alternative: x stochastically smaller than y). Returns
    (D+, p, "exact" or "asymptotic"); the exact/asymptotic rule is R's (module docstring)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m, n = len(x), len(y)
    if m < 1 or n < 1:
        raise ValueError("ks_greater needs at least one value in each sample")
    w = np.concatenate([x, y])
    o = np.argsort(w, kind="stable")
    is_x = o < m
    num = np.cumsum(is_x) * n - np.cumsum(~is_x) * m          # (ECDF_x - ECDF_y) * m * n at each position
    ties = len(np.unique(w)) < m + n
    check = np.r_[np.diff(w[o]) != 0, True] if ties else None
    d_num = int(num[check].max()) if ties else int(num.max())
    d = d_num / (m * n)
    exact = m * n < R_KS_EXACT_BELOW
    if d_num <= 0:                                # includes all values equal (R: q <= 0 gives p = 1)
        p = 1.0
    elif exact:
        p = _smirnov_greater_upper(d_num, m, n, check)
    else:
        p = 1.0 - (-math.expm1(-2.0 * (m * n / (m + n)) * d * d))
    return float(d), float(p), "exact" if exact else "asymptotic"


# ---------------------------------------------------------------- folds

def random_folds(n: int, k: int, seed: int) -> np.ndarray:
    """Random k-fold split of n sites (fold sizes floor(n/k) or ceil(n/k)), ``numpy.random.default_rng(seed)``."""
    return np.random.default_rng(seed).permutation(np.arange(n) % k)


def q_grid(k: int, n: int, nk_len: int) -> np.ndarray:
    """CAST's numbers of clusters: ``round(exp(seq(log(k), log(n - 2), length.out = nk_len)))`` with duplicates
    dropped (R ``seq``: exact end points, interior from + i * by; ``round``: half to even, as ``numpy.rint``)."""
    lo, hi = math.log(k), math.log(n - 2)
    if nk_len == 1:
        s = np.array([lo])
    else:
        s = np.r_[lo, lo + np.arange(1, nk_len - 1) * ((hi - lo) / (nk_len - 1)), hi]
    q = np.rint(np.exp(s)).astype(np.int64)
    _, first = np.unique(q, return_index=True)
    return q[np.sort(first)]


def _roots(parent: np.ndarray) -> np.ndarray:
    r = parent.copy()
    while True:                                   # pointer jumping: every entry reaches its root
        nxt = r[r]
        if np.array_equal(nxt, r):
            return r
        r = nxt


def _find(parent: np.ndarray, a: int) -> int:
    root = a
    while parent[root] != root:
        root = int(parent[root])
    while parent[a] != root:                      # path compression
        parent[a], a = root, int(parent[a])
    return root


def _first_appearance(roots: np.ndarray) -> np.ndarray:
    _, first, inv = np.unique(roots, return_index=True, return_inverse=True)
    rank = np.empty(len(first), dtype=np.int64)
    rank[np.argsort(first, kind="stable")] = np.arange(len(first))
    return rank[inv.ravel()]


def cut_tree_labels(Z: np.ndarray, n: int, qs) -> dict[int, np.ndarray]:
    """R ``cutree(hc, k = q)`` for each q in ``qs``, from a scipy linkage matrix (merges in increasing height):
    the clusters after the first n - q merges, numbered 0.. in order of first appearance in the data."""
    parent = np.arange(n)
    rep = np.concatenate([np.arange(n), np.zeros(max(n - 1, 0), dtype=np.int64)])
    out, done = {}, 0
    for q in sorted({int(v) for v in qs}, reverse=True):          # fewest merges first
        if not 1 <= q <= n:
            raise ValueError(f"cannot cut {n} points into {q} clusters")
        while done < n - q:
            ra, rb = _find(parent, int(rep[int(Z[done, 0])])), _find(parent, int(rep[int(Z[done, 1])]))
            parent[rb] = ra
            rep[n + done] = ra
            done += 1
        out[q] = _first_appearance(_roots(parent))
    return out


def _pc1(lonlat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centre and unit loading of the first principal component of the coordinates (R ``prcomp``, centred, not
    scaled), from the 2 x 2 scatter matrix in closed form; sign fixed so that the larger |loading| is positive."""
    c = lonlat.mean(axis=0)
    x = lonlat - c
    a, b, d = float(np.sum(x[:, 0] ** 2)), float(np.sum(x[:, 0] * x[:, 1])), float(np.sum(x[:, 1] ** 2))
    if b == 0.0:
        v = np.array([1.0, 0.0]) if a >= d else np.array([0.0, 1.0])
    else:
        lam = (a + d) / 2 + math.hypot((a - d) / 2, b)
        u1, u2 = np.array([b, lam - a]), np.array([lam - d, b])
        v = u1 if math.hypot(*u1) >= math.hypot(*u2) else u2
        v = v / math.hypot(*v)
    if v[int(np.argmax(np.abs(v)))] < 0:
        v = -v
    return c, v


def cluster_scores(lonlat: np.ndarray, labels: np.ndarray, centre: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Score of each cluster on the first principal component, at the cluster centroid (lon/lat degrees)."""
    q = int(labels.max()) + 1
    size = np.bincount(labels, minlength=q)
    cx = np.bincount(labels, weights=lonlat[:, 0], minlength=q) / size
    cy = np.bincount(labels, weights=lonlat[:, 1], minlength=q) / size
    return (cx - centre[0]) * v[0] + (cy - centre[1]) * v[1]


def merge_clusters(labels: np.ndarray, scores: np.ndarray, k: int) -> np.ndarray:
    """CAST's merge of q clusters into k folds: clusters ordered by score (stable); each cluster with at least
    n/k sites gets its own fold (0, 1, ... in that order); the others are dealt in that order, cyclically, to
    the remaining folds. Returns the fold of every site."""
    labels = np.asarray(labels)
    n, q = len(labels), int(labels.max()) + 1
    size = np.bincount(labels, minlength=q)
    order = np.argsort(np.asarray(scores, float), kind="stable")
    big = [int(c) for c in order if size[c] >= n / k]
    small = [int(c) for c in order if size[c] < n / k]
    rest = np.arange(len(big), k)
    if small and len(rest) == 0:                  # impossible: k clusters of >= n/k sites hold every site
        raise RuntimeError("internal error: clusters left over after every fold was used")
    fold_of = np.full(q, -1, dtype=np.int64)
    fold_of[big] = np.arange(len(big))
    fold_of[small] = rest[np.arange(len(small)) % max(len(rest), 1)]
    return fold_of[labels]


# ---------------------------------------------------------------- kNNDM

def _validate(n: int, m: int, k: int, maxp: float, clustering: str, linkage: str, nk_len: int,
              ks_alpha: float, earth_radius_km: float) -> None:
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 2:
        raise ValueError(f"k must be an integer >= 2, got {k!r}")
    if not 1.0 / k < maxp < 1.0:
        raise ValueError(f"maxp must be strictly between 1/k = {1.0 / k:.4g} and 1, got {maxp!r} (CAST)")
    if clustering not in ("hierarchical", "kmeans"):
        raise ValueError(f"clustering must be 'hierarchical' or 'kmeans', got {clustering!r}")
    if clustering == "kmeans":
        raise ValueError("kmeans clustering only works with projected coordinates (CAST); use 'hierarchical' "
                         "for lon/lat")
    if linkage not in LINKAGES:
        raise ValueError(f"linkage must be one of {sorted(LINKAGES)}, got {linkage!r}")
    if isinstance(nk_len, bool) or not isinstance(nk_len, (int, np.integer)) or nk_len < 1:
        raise ValueError(f"nk_len must be a positive integer, got {nk_len!r}")
    if not 0.0 < ks_alpha < 1.0:
        raise ValueError(f"ks_alpha must be in (0, 1), got {ks_alpha!r}")
    if not earth_radius_km > 0:
        raise ValueError(f"earth_radius_km must be positive, got {earth_radius_km!r}")
    if n < k + 2:
        raise ValueError(f"kNNDM needs at least k + 2 = {k + 2} training sites, got {n}")
    if m < 1:
        raise ValueError("kNNDM needs at least one prediction point")


def _search(dist: np.ndarray, gij: np.ndarray, lonlat: np.ndarray, k: int, maxp: float, nk_len: int,
            linkage: str) -> dict:
    """Step 3 of the module docstring: the split with the smallest W over the grid of cluster numbers."""
    n = len(dist)
    Z = scipy_linkage(squareform(dist, checks=False), method=LINKAGES[linkage])
    grid = q_grid(k, n, nk_len)
    cuts = cut_tree_labels(Z, n, grid)
    centre, v = _pc1(lonlat)
    best, n_valid = None, 0
    for q in grid:
        labels = cuts[int(q)]
        folds = merge_clusters(labels, cluster_scores(lonlat, labels, centre, v), k)
        if (np.bincount(folds, minlength=k) / n > maxp).any():
            continue
        n_valid += 1
        gstar = cv_distances_km(dist, folds)
        w = wasserstein_stat(gstar, gij)
        if best is None or w < best["W"]:          # first minimum, as R's which.min
            best = {"W": w, "q": int(q), "folds": folds, "gjstar": gstar}
    if best is None:
        raise RuntimeError(f"kNNDM: no split into {k} folds keeps every fold within maxp = {maxp} of the {n} "
                           "sites; increase maxp or decrease k (CAST's advice)")
    best.update(n_grid=len(grid), n_valid=n_valid, q_min=int(grid[0]), q_max=int(grid[-1]))
    return best


def knndm_core(dist: np.ndarray, gij: np.ndarray, gj: np.ndarray, lonlat: np.ndarray, k: int, maxp: float,
               seed: int, nk_len: int, linkage: str, ks_alpha: float) -> tuple[np.ndarray, dict]:
    """kNNDM from precomputed distances (site-to-site matrix ``dist``, ``Gij``, ``Gj``, same unit); ``lonlat``
    only orders the clusters. ``knndm_folds`` is the entry point; this core also lets a check run the same
    algorithm on other distances (e.g. ellipsoidal ones)."""
    n = len(dist)
    d_ks, p_ks, ks_kind = ks_greater(gj, gij)
    rand = random_folds(n, k, seed)
    gstar_rand = cv_distances_km(dist, rand)
    w_rand = wasserstein_stat(gstar_rand, gij)
    out = {"ks": {"D": d_ks, "p": p_ks, "test": ks_kind, "alpha": ks_alpha}, "W_random": w_rand,
           "gjstar_random": gstar_rand}
    if p_ks >= ks_alpha:
        out.update(random_cv=True, W=w_rand, q=None, folds=rand, gjstar=gstar_rand, n_grid=None, n_valid=None,
                   q_min=None, q_max=None)
    else:
        out.update(random_cv=False, **_search(dist, gij, lonlat, k, maxp, nk_len, linkage))
    return out["folds"], out


def _method(r: dict, k: int, maxp: float, linkage: str, n: int) -> str:
    ks = r["ks"]
    test = f"one-sided KS test of Gj < Gij ({ks['test']}): p = {ks['p']:.3g}"
    if r["random_cv"]:
        return (f"random {k}-fold CV, CAST's kNNDM fallback: the sites are not more clustered than the "
                f"prediction points ({test} >= {ks['alpha']})")
    return (f"kNNDM (port of CAST {CAST_VERSION} knndm_geo), {test} < {ks['alpha']}: hierarchical clustering "
            f"({linkage}) of great-circle distances cut into q = {r['q']} clusters, merged into {k} folds with "
            f"at most {maxp} of the {n} sites each; q has the smallest W among {r['n_valid']} valid of "
            f"{r['n_grid']} grid values {r['q_min']}..{r['q_max']}")


def knndm_folds(train_lonlat: np.ndarray, pred_lonlat: np.ndarray, k: int, maxp: float = 0.5,
                clustering: str = "hierarchical", seed: int = 0, *, earth_radius_km: float = 6371.0,
                nk_len: int = 100, linkage: str = "ward.D2", ks_alpha: float = 0.05) -> tuple[np.ndarray, dict]:
    """kNNDM k-fold split of the training sites ``train_lonlat`` (n x 2, lon/lat degrees) for predictions at
    ``pred_lonlat`` (m x 2): fold ids 0..k-1 (length n) and an info dict (JSON-ready). Defaults of ``maxp``,
    ``nk_len``, ``linkage`` and ``ks_alpha`` are CAST's; callers pass the configured values (module docstring).

    info: ``W`` (statistic of the returned split, km), ``W_random`` (random split, same seed), ``q`` (number of
    clusters chosen; None for the random fallback), ``random_cv``, ``method``, ``source`` (CAST version and the
    SHA-256 of the knndm.R read), ``n_train``, ``n_pred``, the medians of Gij, Gj, Gjstar and of the random
    split's Gjstar (km), ``fold_sizes``, the KS test, the grid summary and the parameters used."""
    x = _lonlat(train_lonlat, "train_lonlat")
    p = _lonlat(pred_lonlat, "pred_lonlat")
    _validate(len(x), len(p), k, maxp, clustering, linkage, nk_len, ks_alpha, earth_radius_km)
    k, nk_len = int(k), int(nk_len)
    dist = pairwise_km(x, earth_radius_km)
    gij = nearest_km(x, p, earth_radius_km)
    gj = nearest_km(x, None, earth_radius_km)
    folds, r = knndm_core(dist, gij, gj, x, k, float(maxp), int(seed), nk_len, linkage, float(ks_alpha))
    info = {
        "W": float(r["W"]), "W_random": float(r["W_random"]), "q": r["q"], "random_cv": bool(r["random_cv"]),
        "method": _method(r, k, maxp, linkage, len(x)), "source": SOURCE,
        "n_train": int(len(x)), "n_pred": int(len(p)),
        "Gij_median_km": float(np.median(gij)), "Gj_median_km": float(np.median(gj)),
        "Gjstar_median_km": float(np.median(r["gjstar"])),
        "Gjstar_random_median_km": float(np.median(r["gjstar_random"])),
        "fold_sizes": [int(c) for c in np.bincount(folds, minlength=k)],
        "ks": dict(r["ks"]),
        "q_grid": None if r["random_cv"] else {"n_values": int(r["n_grid"]), "n_valid": int(r["n_valid"]),
                                               "min": r["q_min"], "max": r["q_max"]},
        "k": k, "maxp": float(maxp), "clustering": clustering, "linkage": linkage, "nk_len": nk_len,
        "seed": int(seed), "earth_radius_km": float(earth_radius_km), "distance": "great-circle (haversine), km",
    }
    return folds.astype(np.int64), info


def fold_match(train_lonlat, pred_lonlat, folds, earth_radius_km: float = 6371.0) -> dict:
    """How well any split of the sites (e.g. 5-degree blocks, random folds) matches the prediction situation:
    W between its CV distances and Gij (km; the statistic kNNDM minimises) and the medians of Gjstar and Gij.
    Comparable with ``knndm_folds``' W for the same sites and prediction points."""
    x = _lonlat(train_lonlat, "train_lonlat")
    f = np.asarray(folds)
    if f.shape != (len(x),):
        raise ValueError(f"folds must have one entry per training site ({len(x)}), got shape {f.shape}")
    gij = nearest_km(x, pred_lonlat, earth_radius_km)
    gstar = cv_distances_km(pairwise_km(x, earth_radius_km), f)
    return {"W": wasserstein_stat(gstar, gij), "Gjstar_median_km": float(np.median(gstar)),
            "Gij_median_km": float(np.median(gij)), "n_folds": int(len(np.unique(f)))}
