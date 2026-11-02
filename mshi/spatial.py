"""Spatial helpers shared by all stages: block labels, block CV folds, 5-km clustering, bootstraps.

These reproduce the handoff prototype exactly (block labels are strings sorted lexicographically by
``np.unique`` and then shuffled by a seeded generator), because fold assignment and bootstrap draws
depend on that order.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.metrics import r2_score
from sklearn.neighbors import BallTree


def block_labels(lon, lat, deg: float) -> np.ndarray:
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    return np.char.add(np.char.add(np.floor(lon / deg).astype(int).astype(str), "_"),
                       np.floor(lat / deg).astype(int).astype(str))


def block_folds(lon, lat, seed: int, deg: float = 5.0, k: int = 5) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Spatial-block K-fold: blocks of ``deg`` x ``deg`` degrees shuffled (seeded) into ``k`` folds.

    Yields (train_idx, valid_idx). If there are fewer blocks than ``k``, uses one fold per block.
    """
    b = block_labels(lon, lat, deg)
    u = np.unique(b)
    rng = np.random.default_rng(seed)
    rng.shuffle(u)
    for vb in np.array_split(u, min(k, len(u))):
        m = np.isin(b, vb)
        yield np.where(~m)[0], np.where(m)[0]


def cluster_within_km(lat, lon, radius_km: float, earth_radius_km: float = 6371.0) -> np.ndarray:
    """Connected components of the graph linking points within ``radius_km`` (haversine).

    Note: components can chain, so two records in one site may be more than ``radius_km`` apart.
    """
    X = np.radians(np.c_[np.asarray(lat, float), np.asarray(lon, float)])
    if len(X) == 0:
        return np.zeros(0, dtype=int)
    tree = BallTree(X, metric="haversine")
    nb = tree.query_radius(X, r=radius_km / earth_radius_km)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)])
    cols = np.concatenate(nb)
    A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(X), len(X)))
    _, lab = connected_components(A, directed=False)
    return lab


def bootstrap_ci(y, p, n: int = 2000, seed: int = 42, lon=None, lat=None, deg: float | None = None,
                 stat: Callable[[np.ndarray, np.ndarray], float] = r2_score, alpha: float = 0.05) -> list[float]:
    """Percentile CI of ``stat(y, p)`` under a site bootstrap (deg=None) or a spatial-block bootstrap."""
    y = np.asarray(y)
    p = np.asarray(p)
    rng = np.random.default_rng(seed)
    if deg is None:
        bs = [stat(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    else:
        b = block_labels(lon, lat, deg)
        u = np.unique(b)
        idx = {k: np.where(b == k)[0] for k in u}
        bs = []
        for _ in range(n):
            i = np.concatenate([idx[k] for k in rng.choice(u, len(u))])
            bs.append(stat(y[i], p[i]))
    return [float(np.quantile(bs, alpha / 2)), float(np.quantile(bs, 1 - alpha / 2))]
