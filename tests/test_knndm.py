"""kNNDM folds (mshi.analysis.knndm): the toy cases the brief asks for (Phase 2 item 2: "implement it from the
paper and test it on a toy case") and unit checks of the port of CAST 1.2.0 knndm.R. Everything is synthetic
and offline; nothing is written outside pytest's tmp_path.

(a) clustered sites, prediction points spread over a larger area: kNNDM's W < random CV's W, and its CV
    distances are closer to the prediction distances; (b) sites drawn from the prediction domain itself: random
    CV (CAST's fallback), or a split that behaves like it; (c) fold ids 0..k-1, every fold non-empty, largest
    fold <= maxp * n, deterministic for a seed (byte-identical JSON); (d) haversine distances on known pairs.
"""
import copy
import itertools
import math

import numpy as np
import pytest
from scipy import stats
from scipy.cluster.hierarchy import cut_tree
from scipy.cluster.hierarchy import linkage as scipy_linkage
from scipy.spatial.distance import squareform

from mshi.analysis import knndm as kn
from mshi.analysis.knndm import (cv_distances_km, fold_match, haversine_km, knndm_folds, ks_greater,
                                 merge_clusters, nearest_km, pairwise_km, q_grid, random_folds, wasserstein_stat)
from mshi.config import load_config
from mshi.io import write_json
from mshi.spatial import block_folds

R = 6371.0
K, MAXP, SEED = 5, 0.5, 42
SPEC_KEYS = {"W", "W_random", "q", "method", "source", "n_train", "n_pred", "Gij_median_km", "Gjstar_median_km"}


def sphere_box(rng, n, lon=(0.0, 30.0), lat=(35.0, 60.0)) -> np.ndarray:
    """n points (lon, lat), uniform by area in a lon/lat box."""
    s0, s1 = np.sin(np.radians(lat[0])), np.sin(np.radians(lat[1]))
    return np.c_[rng.uniform(*lon, n), np.degrees(np.arcsin(rng.uniform(s0, s1, n)))]


@pytest.fixture(scope="module")
def domain():
    """2,000 prediction points spread over a 30 x 25 degree box (about 2,600 x 2,800 km)."""
    return sphere_box(np.random.default_rng(3), 2000)


@pytest.fixture(scope="module")
def clustered():
    """150 sites in six tight clusters (sd 0.15 degree, about 15 km) inside the same box."""
    rng = np.random.default_rng(4)
    return np.concatenate([c + rng.normal(0.0, 0.15, (25, 2)) for c in sphere_box(rng, 6)])


@pytest.fixture(scope="module")
def random_sites(domain):
    """150 sites drawn at random from the prediction points themselves."""
    return domain[np.random.default_rng(5).choice(len(domain), 150, replace=False)]


@pytest.fixture(scope="module")
def dominant():
    """150 sites, 70% of them in one tight cluster (a single cluster would exceed maxp = 0.5)."""
    rng = np.random.default_rng(6)
    return np.concatenate([np.array([15.0, 47.0]) + rng.normal(0.0, 0.2, (105, 2)), sphere_box(rng, 45)])


def run(sites, pred, **kw):
    args = dict(k=K, maxp=MAXP, clustering="hierarchical", seed=SEED, earth_radius_km=R)
    args.update(kw)
    return knndm_folds(sites, pred, **args)


# ---------------------------------------------------------------- (a) clustered sites

def test_a_clustered_sites_knndm_matches_prediction_distances_better_than_random_cv(clustered, domain):
    folds, info = run(clustered, domain)
    assert SPEC_KEYS <= set(info)
    assert not info["random_cv"] and info["ks"]["p"] < info["ks"]["alpha"]
    assert isinstance(info["q"], int) and K <= info["q"] <= len(clustered) - 2
    assert info["W"] < info["W_random"]
    gij = nearest_km(clustered, domain, R)
    dist = pairwise_km(clustered, R)
    g_knndm = cv_distances_km(dist, folds)
    g_random = cv_distances_km(dist, random_folds(len(clustered), K, SEED))
    assert info["W"] == pytest.approx(wasserstein_stat(g_knndm, gij), rel=1e-12)
    assert info["W_random"] == pytest.approx(wasserstein_stat(g_random, gij), rel=1e-12)
    assert info["Gjstar_median_km"] == pytest.approx(np.median(g_knndm), rel=1e-12)
    assert info["Gij_median_km"] == pytest.approx(np.median(gij), rel=1e-12)
    # CV distances closer to the prediction distances than random CV's: median gap and KS distance
    med = np.median(gij)
    assert abs(np.median(g_knndm) - med) < abs(np.median(g_random) - med)
    assert stats.ks_2samp(g_knndm, gij).statistic < stats.ks_2samp(g_random, gij).statistic
    # random CV interpolates within the clusters here: its CV distances are far below the prediction distances
    assert np.median(g_random) < 0.1 * med


# ---------------------------------------------------------------- (b) sites drawn from the prediction domain

def test_b_sites_drawn_from_the_prediction_domain_fall_back_to_random_cv(random_sites, domain):
    folds, info = run(random_sites, domain)
    assert info["random_cv"] and info["q"] is None and info["ks"]["p"] >= info["ks"]["alpha"]
    assert np.array_equal(folds, random_folds(len(random_sites), K, SEED))
    assert info["W"] == info["W_random"] and info["q_grid"] is None
    assert info["method"].startswith(f"random {K}-fold CV")


@pytest.mark.parametrize("seed", range(8))
def test_b_independently_drawn_sites_behave_like_random_cv(seed):
    """Sites drawn independently from the prediction points' distribution. CAST's KS test rejects here more
    often than its nominal 5% (about a third of the leave-one-out distances are duplicates, from mutual nearest
    neighbours); when it does, kNNDM picks a near-singleton clustering (q close to n), a near-random split.
    Either way the split matches the prediction distances as random CV does: over 100 such draws W was at most
    0.33 of the median Gij, against 1.04 for random CV on the clustered sites of (a)."""
    rng = np.random.default_rng(100 + seed)
    pred = sphere_box(rng, 2000)
    sites = sphere_box(rng, 150)
    _, info = run(sites, pred)
    if not info["random_cv"]:
        assert info["q"] >= 0.9 * len(sites)
    assert info["W"] <= 0.5 * info["Gij_median_km"]
    assert info["W_random"] <= 0.5 * info["Gij_median_km"]


def test_b_ks_alpha_decides_the_fallback(random_sites, domain):
    _, info = run(random_sites, domain)
    p = info["ks"]["p"]
    assert p < 1.0
    _, forced = run(random_sites, domain, ks_alpha=(1.0 + p) / 2)      # p < alpha: the clustering search runs
    assert not forced["random_cv"] and forced["q"] is not None


# ---------------------------------------------------------------- (c) fold properties, determinism

@pytest.mark.parametrize("case", ["clustered", "dominant", "random_sites"])
@pytest.mark.parametrize("maxp", [0.3, 0.5, 0.75])
def test_c_folds_complete_within_maxp_and_deterministic(case, maxp, request, domain, tmp_path):
    sites = request.getfixturevalue(case)
    f1, i1 = run(sites, domain, maxp=maxp)
    f2, i2 = run(sites.copy(), domain.copy(), maxp=maxp)
    assert f1.dtype.kind == "i" and f1.shape == (len(sites),)
    assert sorted(set(f1.tolist())) == list(range(K))
    sizes = np.bincount(f1, minlength=K)
    assert sizes.min() >= 1 and sizes.max() <= maxp * len(sites)
    assert i1["fold_sizes"] == sizes.tolist()
    assert np.array_equal(f1, f2)
    a, b = write_json(i1, tmp_path / "a.json"), write_json(i2, tmp_path / "b.json")
    assert a.read_bytes() == b.read_bytes()


def test_c_maxp_skips_splits_with_a_dominant_fold(dominant, domain):
    _, info = run(dominant, domain)
    assert not info["random_cv"]
    assert info["q_grid"]["n_valid"] < info["q_grid"]["n_values"]       # some cuts put > half the sites in a fold
    assert max(info["fold_sizes"]) <= MAXP * len(dominant)


def test_c_no_split_within_maxp_is_an_error(domain):
    rng = np.random.default_rng(7)
    pairs = np.repeat(sphere_box(rng, 3), 2, axis=0) + rng.normal(0.0, 0.01, (6, 2))
    sites = np.concatenate([pairs, sphere_box(rng, 1)])               # n = 7 = k + 2: the only cut is q = 5
    with pytest.raises(RuntimeError, match="maxp"):
        run(sites, domain, maxp=0.21)


def test_c_seed_sets_only_the_random_split(clustered, random_sites, domain):
    f1, i1 = run(clustered, domain, seed=1)
    f2, i2 = run(clustered, domain, seed=2)
    assert np.array_equal(f1, f2) and i1["W"] == i2["W"] and i1["q"] == i2["q"]
    assert i1["W_random"] != i2["W_random"]
    r1, _ = run(random_sites, domain, seed=1)
    r2, _ = run(random_sites, domain, seed=2)
    assert not np.array_equal(r1, r2)
    assert sorted(np.bincount(r1).tolist()) == [30] * 5 == sorted(np.bincount(r2).tolist())


def test_c_earth_radius_scales_w_only(clustered, domain):
    f1, i1 = run(clustered, domain)
    f2, i2 = run(clustered, domain, earth_radius_km=2 * R)
    assert np.array_equal(f1, f2) and i1["q"] == i2["q"] and i1["ks"]["p"] == i2["ks"]["p"]
    assert i2["W"] == pytest.approx(2 * i1["W"], rel=1e-9)
    assert i2["W_random"] == pytest.approx(2 * i1["W_random"], rel=1e-9)


# ---------------------------------------------------------------- (d) distances

def test_d_haversine_on_known_pairs():
    one_deg = math.pi / 180.0 * R
    assert one_deg == pytest.approx(111.195, abs=1e-3)
    assert haversine_km(0, 0, 0, 1) == pytest.approx(one_deg, rel=1e-12)          # 1 degree of latitude
    assert haversine_km(10, 45, 10, 46) == pytest.approx(one_deg, rel=1e-12)
    assert haversine_km(0, 0, 1, 0) == pytest.approx(one_deg, rel=1e-12)          # 1 degree of longitude, equator
    assert haversine_km(179.5, 0, -179.5, 0) == pytest.approx(one_deg, rel=1e-12)  # across the antimeridian
    at60 = 2 * R * math.asin(math.cos(math.radians(60)) * math.sin(math.radians(0.5)))
    assert at60 == pytest.approx(55.6, abs=0.01)
    assert haversine_km(0, 60, 1, 60) == pytest.approx(at60, rel=1e-12)           # 1 degree of longitude at 60N
    assert haversine_km(0, 0, 180, 0) == pytest.approx(math.pi * R, rel=1e-12)    # half the circumference
    assert haversine_km(0, 90, 0, -90) == pytest.approx(math.pi * R, rel=1e-12)
    assert haversine_km(0, 0, 0, 1, earth_radius_km=6371.01) == pytest.approx(one_deg * 6371.01 / R, rel=1e-12)


def test_d_balltree_and_matrix_distances_agree_with_haversine():
    rng = np.random.default_rng(9)
    a = np.c_[rng.uniform(-180, 180, 80), rng.uniform(-80, 80, 80)]
    b = np.c_[rng.uniform(-180, 180, 300), rng.uniform(-80, 80, 300)]
    full_ba = haversine_km(b[:, None, 0], b[:, None, 1], a[None, :, 0], a[None, :, 1])
    assert np.allclose(nearest_km(a, b), full_ba.min(axis=1), rtol=1e-10, atol=1e-9)
    D = pairwise_km(a)
    assert np.allclose(D, haversine_km(a[:, None, 0], a[:, None, 1], a[None, :, 0], a[None, :, 1]),
                       rtol=1e-10, atol=1e-9)
    assert np.array_equal(D, D.T) and np.all(np.diag(D) == 0.0)
    loo = nearest_km(a)
    assert np.allclose(loo, (D + np.diag(np.full(len(a), np.inf))).min(axis=1), rtol=1e-12)
    assert np.allclose(cv_distances_km(D, np.arange(len(a))), loo, rtol=1e-12)    # one site per fold = LOO
    assert nearest_km([[0.0, 0.0]], [[0.0, 1.0]])[0] == pytest.approx(math.pi / 180.0 * R, rel=1e-12)
    across = nearest_km([[179.95, -17.0], [100.0, -17.0]], [[-179.95, -17.0]])[0]
    assert across == pytest.approx(haversine_km(179.95, -17.0, -179.95, -17.0), rel=1e-12) and across < 11.0
    dup = nearest_km([[5.0, 5.0], [5.0, 5.0], [6.0, 5.0]])
    assert dup[0] == 0.0 and dup[1] == 0.0                                        # duplicated location


# ---------------------------------------------------------------- the two statistics (R and twosamples)

def _brute_ks_greater(x, y) -> tuple[float, float]:
    """D+ and its exact p-value by enumerating every assignment of the pooled sorted values to x and y (the
    permutation distribution given the ties); D+ is evaluated where the pooled sample changes value."""
    m, n = len(x), len(y)
    w = np.concatenate([x, y])
    check = np.r_[np.diff(np.sort(w, kind="stable")) != 0, True]

    def dplus(xpos) -> int:
        is_x = np.zeros(m + n, dtype=bool)
        is_x[list(xpos)] = True
        return int((np.cumsum(is_x) * n - np.cumsum(~is_x) * m)[check].max())

    obs = dplus(np.where(np.argsort(w, kind="stable") < m)[0])
    ds = np.array([dplus(c) for c in itertools.combinations(range(m + n), m)])
    return obs / (m * n), float(np.mean(ds >= obs))


@pytest.mark.parametrize("x,y", [
    ([0.1, 0.4, 0.5, 0.9], [0.3, 0.6, 0.7, 1.2, 1.5]),
    ([1, 2, 2, 3], [2, 3, 3, 4, 5]),                                  # ties within and across the samples
    ([0.5, 0.2, 0.9, 0.1, 0.3, 0.4], [0.8, 1.0, 0.6, 0.7, 1.1, 0.95, 0.65]),
    ([2, 2, 2, 5], [1, 1, 3, 3, 4]),
    ([4, 5, 6], [1, 2, 3, 3]),                                        # x larger: D+ = 0, p = 1
])
def test_ks_greater_exact_is_the_permutation_distribution(x, y):
    d, p, kind = ks_greater(x, y)
    d_ref, p_ref = _brute_ks_greater(np.asarray(x, float), np.asarray(y, float))
    assert kind == "exact" and d == pytest.approx(d_ref, abs=1e-15) and p == pytest.approx(p_ref, rel=1e-12)


def test_ks_greater_matches_scipy_exact_and_r_asymptotic_formula():
    rng = np.random.default_rng(11)
    x, y = rng.normal(0.0, 1.0, 30), rng.normal(0.4, 1.0, 40)                # 30 * 40 < 10000: exact
    d, p, kind = ks_greater(x, y)
    ref = stats.ks_2samp(x, y, alternative="greater", method="exact")
    assert kind == "exact" and d == pytest.approx(ref.statistic) and p == pytest.approx(ref.pvalue, rel=1e-9)
    x, y = rng.normal(0.0, 1.0, 100), rng.normal(0.2, 1.0, 200)              # 100 * 200 >= 10000: asymptotic
    d, p, kind = ks_greater(x, y)
    assert kind == "asymptotic" and d == pytest.approx(stats.ks_2samp(x, y, alternative="greater").statistic)
    assert p == pytest.approx(math.exp(-2.0 * (100 * 200 / 300) * d * d), rel=1e-12)
    assert ks_greater(rng.normal(0.0, 1.0, 200), rng.normal(1.0, 1.0, 200))[1] < 1e-6   # x smaller than y
    assert ks_greater(rng.normal(1.0, 1.0, 200), rng.normal(0.0, 1.0, 200))[1] > 0.5


def test_wasserstein_stat_is_the_1_wasserstein_distance():
    rng = np.random.default_rng(12)
    a, b = rng.gamma(2.0, 50.0, 300), rng.gamma(3.0, 40.0, 1000)
    assert wasserstein_stat(a, b) == pytest.approx(stats.wasserstein_distance(a, b), rel=1e-12)
    a2, b2 = np.round(a, -1), np.round(b, -1)                                  # with ties
    assert wasserstein_stat(a2, b2) == pytest.approx(stats.wasserstein_distance(a2, b2), rel=1e-12)
    assert wasserstein_stat(a, a) == 0.0
    assert wasserstein_stat([0.0, 2.0], [1.0, 3.0]) == pytest.approx(1.0)      # |F_a - F_b| = 0.5 on [0,1), [2,3)


# ---------------------------------------------------------------- pieces of CAST's algorithm

def test_merge_rule_is_casts():
    labels = np.repeat(np.arange(5), [6, 2, 3, 5, 4])          # 20 sites, k = 4: clusters of >= 5 sites are "big"
    scores = np.array([0.5, -1.0, 2.0, -0.5, 1.0])              # order by score: c1, c3, c0, c4, c2
    folds = merge_clusters(labels, scores, 4)
    fold_of = {c: int(folds[labels == c][0]) for c in range(5)}
    assert fold_of == {3: 0, 0: 1, 1: 2, 4: 3, 2: 2}           # big c3, c0 own folds; c1, c4, c2 dealt to 2, 3, 2
    assert np.bincount(folds).tolist() == [5, 6, 5, 4]
    tied = merge_clusters(np.repeat(np.arange(6), 2), np.zeros(6), 4)
    assert tied.tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 0, 0, 1, 1]  # equal scores keep the cluster numbering


def test_cut_tree_labels_are_r_cutree():
    x = sphere_box(np.random.default_rng(13), 60)
    Z = scipy_linkage(squareform(pairwise_km(x), checks=False), method="ward")
    qs = [5, 9, 20, 58]
    mine = kn.cut_tree_labels(Z, 60, qs)
    ref = cut_tree(Z, n_clusters=qs)
    for i, q in enumerate(qs):
        assert np.array_equal(mine[q], ref[:, i])
        first = np.unique(mine[q], return_index=True)[1]
        assert len(first) == q and np.all(np.diff(first) > 0)    # numbered by first appearance, as R's cutree


def test_q_grid_is_casts():
    assert q_grid(5, 12, 4).tolist() == [5, 6, 8, 10]          # round(5 * 2^(i/3)), i = 0..3
    g = q_grid(5, 150, 100)
    assert g[0] == 5 and g[-1] == 148 and np.all(np.diff(g) > 0) and len(g) <= 100
    assert q_grid(5, 7, 100).tolist() == [5]
    assert q_grid(5, 150, 1).tolist() == [5]


def test_fold_match_scores_any_split(clustered, domain):
    folds, info = run(clustered, domain)
    assert fold_match(clustered, domain, folds, R)["W"] == pytest.approx(info["W"], rel=1e-12)
    rnd = fold_match(clustered, domain, random_folds(len(clustered), K, SEED), R)
    assert rnd["W"] == pytest.approx(info["W_random"], rel=1e-12)
    blocks = np.empty(len(clustered), dtype=int)                # the benchmark's other design: 5-degree blocks
    for i, (_, va) in enumerate(block_folds(clustered[:, 0], clustered[:, 1], SEED, 5.0, K)):
        blocks[va] = i
    bw = fold_match(clustered, domain, blocks, R)
    assert bw["n_folds"] == len(np.unique(blocks)) and bw["W"] > 0.0


# ---------------------------------------------------------------- arguments and configuration

@pytest.mark.parametrize("kwargs,match", [
    (dict(maxp=0.2), "maxp"), (dict(maxp=1.0), "maxp"), (dict(k=1), "k must"),
    (dict(clustering="kmeans"), "projected"), (dict(clustering="pam"), "clustering"),
    (dict(linkage="centroid"), "linkage"), (dict(nk_len=0), "nk_len"), (dict(ks_alpha=0.0), "ks_alpha"),
])
def test_invalid_arguments_are_refused(clustered, domain, kwargs, match):
    with pytest.raises(ValueError, match=match):
        run(clustered, domain, **kwargs)


def test_invalid_coordinates_are_refused(clustered, domain):
    bad = clustered.copy()
    bad[3, 1] = np.nan
    with pytest.raises(ValueError, match="missing"):
        run(bad, domain)
    bad[3, 1] = 95.0
    with pytest.raises(ValueError, match="latitudes"):
        run(bad, domain)
    with pytest.raises(ValueError, match="shape"):
        run(clustered[:, :1], domain)
    with pytest.raises(ValueError, match="k \\+ 2"):
        run(clustered[:6], domain)
    with pytest.raises(ValueError, match="prediction point"):
        run(clustered, domain[:0])


def test_configured_parameters_are_accepted(clustered, domain):
    """How a stage calls it: k, maxp, clustering and seed from phase2.within.knndm, the radius from site_build;
    nk_len, linkage and ks_alpha are proposed config keys (CAST's values), set here on a copy of the config."""
    data = copy.deepcopy(load_config().data)
    kc = data["phase2"]["within"]["knndm"]
    kc.update(nk_len=100, linkage="ward.D2", ks_alpha=0.05)
    folds, info = knndm_folds(clustered, domain, kc["k"], kc["maxp"], kc["clustering"], kc["seed"],
                              earth_radius_km=data["site_build"]["earth_radius_km"], nk_len=kc["nk_len"],
                              linkage=kc["linkage"], ks_alpha=kc["ks_alpha"])
    assert (info["k"], info["maxp"], info["seed"]) == (kc["k"], kc["maxp"], kc["seed"])
    assert info["earth_radius_km"] == data["site_build"]["earth_radius_km"]
    assert info["source"] == f"CAST 1.2.0 knndm.R sha256 {kn.CAST_KNNDM_SHA256}"
    assert len(folds) == len(clustered)
