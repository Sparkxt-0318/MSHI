"""Check 1: mshi.analysis.knndm.knndm_folds vs an independent literal re-derivation of CAST 1.2.0 knndm_geo
(rcast.py) on many random configurations: KS statistic and p-value, fallback decision, the grid of cluster
numbers, W per valid q, the chosen q, W, Gjstar and the fold partition. Also: naive ward.D2 vs scipy ward,
R cutree vs cut_tree_labels, PCA-sign invariance of the partition."""
import sys
import time

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/scripts")
import numpy as np
from scipy.cluster.hierarchy import linkage

import rcast
from mshi.analysis import knndm as kn

R = 6371.0


def sphere_box(rng, n, lon=(0.0, 30.0), lat=(35.0, 60.0)):
    s0, s1 = np.sin(np.radians(lat[0])), np.sin(np.radians(lat[1]))
    return np.c_[rng.uniform(*lon, n), np.degrees(np.arcsin(rng.uniform(s0, s1, n)))]


def clustered(rng, n, ncl, sd, lon=(0.0, 30.0), lat=(35.0, 60.0)):
    cen = sphere_box(rng, ncl, lon, lat)
    lab = rng.integers(0, ncl, n)
    return cen[lab] + rng.normal(0, sd, (n, 2))


def compare(sites, pred, k, maxp, nk_len, seed=42):
    f, info = kn.knndm_folds(sites, pred, k, maxp, "hierarchical", seed, earth_radius_km=R, nk_len=nk_len)
    rand = kn.random_folds(len(sites), k, seed) + 1
    r = rcast.knndm_geo(sites, pred, k, maxp, nk_len, R=R, rand=rand)
    out = {"n": len(sites), "k": k, "maxp": maxp, "nk_len": nk_len}
    out["ks_D_diff"] = abs(info["ks"]["D"] - r["ks_D"])
    out["ks_p_rel"] = abs(info["ks"]["p"] - r["ks_p"]) / max(r["ks_p"], 1e-300)
    out["random_same"] = info["random_cv"] == r["random"]
    out["random"] = r["random"]
    if r["random"] or info["random_cv"]:
        out["part_same"] = rcast.same_partition(f, r["clust"]) if out["random_same"] else False
        out["W_rel"] = abs(info["W"] - r["W"]) / r["W"]
        out["q_same"] = True
        return out
    out["q_same"] = info["q"] == r["q"]
    out["W_rel"] = abs(info["W"] - r["W"]) / r["W"]
    out["part_same"] = rcast.same_partition(f, r["clust"])
    out["labels_equal_minus1"] = bool(np.array_equal(f, r["clust"] - 1))
    gq = kn.q_grid(k, len(sites), nk_len)
    out["grid_same"] = gq.tolist() == r["grid"]
    out["n_valid_same"] = info["q_grid"]["n_valid"] == len(r["Wgrid"])
    # W for each valid q from the port's pieces
    dist = kn.pairwise_km(sites, R)
    gij = kn.nearest_km(sites, pred, R)
    Z = linkage(dist[np.triu_indices(len(sites), 1)], method="ward")
    cuts = kn.cut_tree_labels(Z, len(sites), gq)
    c, v = kn._pc1(np.asarray(sites, float))
    maxdiff = 0.0
    for q, w in r["Wgrid"].items():
        fl = kn.merge_clusters(cuts[q], kn.cluster_scores(np.asarray(sites, float), cuts[q], c, v), k)
        if (np.bincount(fl, minlength=k) / len(sites) > maxp).any():
            maxdiff = np.inf
            continue
        wq = kn.wasserstein_stat(kn.cv_distances_km(dist, fl), gij)
        maxdiff = max(maxdiff, abs(wq - w) / max(w, 1e-12))
    out["Wgrid_maxrel"] = maxdiff
    return out


def main():
    rng = np.random.default_rng(2026)
    rows = []
    t0 = time.time()
    cases = []
    for i in range(60):
        kind = ["clustered", "dominant", "random", "line", "two_scale"][i % 5]
        n = int(rng.integers(8, 160))
        k = int(rng.integers(2, 11))
        if n < k + 2:
            n = k + 2
        maxp = float(rng.choice([1.0 / k + 0.02, 0.3, 0.5, 0.75, 0.95]))
        if not 1.0 / k < maxp < 1.0:
            maxp = 0.5 if 1.0 / k < 0.5 else min(0.95, 1.0 / k + 0.1)
        nk_len = int(rng.choice([1, 2, 3, 10, 100]))
        pred = sphere_box(rng, int(rng.choice([50, 120, 800])), lon=(-10, 40), lat=(30, 65))
        if kind == "clustered":
            s = clustered(rng, n, max(2, n // 15), 0.2)
        elif kind == "dominant":
            m = int(0.7 * n)
            s = np.r_[np.array([15.0, 47.0]) + rng.normal(0, 0.2, (m, 2)), sphere_box(rng, n - m)]
        elif kind == "random":
            s = pred[rng.choice(len(pred), min(n, len(pred)), replace=False)]
        elif kind == "line":
            s = np.c_[np.linspace(0, 30, n) + rng.normal(0, 0.01, n), 45 + rng.normal(0, 0.3, n)]
        else:
            s = np.r_[clustered(rng, n // 2, 3, 0.05), sphere_box(rng, n - n // 2)]
        cases.append((kind, s, pred, k, maxp, nk_len))
    for kind, s, pred, k, maxp, nk_len in cases:
        try:
            o = compare(s, pred, k, maxp, nk_len)
            o["kind"] = kind
        except Exception as e:  # noqa: BLE001
            o = {"kind": kind, "n": len(s), "k": k, "maxp": maxp, "nk_len": nk_len, "error": f"{type(e).__name__}: {e}"}
        rows.append(o)
    bad = []
    for o in rows:
        if "error" in o:
            print("ERR", o)
            continue
        ok = (o["random_same"] and o["q_same"] and o["part_same"] and o["W_rel"] < 1e-9 and o["ks_D_diff"] < 1e-12
              and o["ks_p_rel"] < 1e-8 and (o["random"] or (o["grid_same"] and o["n_valid_same"]
                                                           and o["Wgrid_maxrel"] < 1e-9)))
        if not ok:
            bad.append(o)
    print(f"{len(rows)} cases, {sum('error' in o for o in rows)} errors, {len(bad)} mismatches, "
          f"{sum(o.get('random', False) for o in rows)} random fallbacks, {time.time() - t0:.1f}s")
    for o in bad:
        print("MISMATCH", o)
    lab = [o.get("labels_equal_minus1") for o in rows if "labels_equal_minus1" in o]
    print("fold labels identical to R's cluster ids - 1 (same PC sign as numpy SVD):", sum(bool(x) for x in lab), "of", len(lab))
    ksmax = max(o["ks_p_rel"] for o in rows if "ks_p_rel" in o)
    print("max relative KS p difference:", ksmax, " exact KS cases:",
          sum(1 for o in rows if "ks_p_rel" in o and o["n"] * 1 < 10000))

    # naive ward.D2 vs scipy ward on great-circle distances, and R cutree vs cut_tree_labels
    nbad = 0
    for i in range(25):
        n = int(rng.integers(5, 45))
        s = clustered(rng, n, max(2, n // 6), 0.5, lon=(-170, 170), lat=(-60, 70)) if i % 2 else sphere_box(rng, n, (60, 150), (-10, 60))
        D = rcast.gc_matrix(s, s, R)
        np.fill_diagonal(D, 0.0)
        D = (D + D.T) / 2
        m_naive, h_naive = rcast.naive_ward_d2(D)
        Z = linkage(D[np.triu_indices(n, 1)], method="ward")
        if not np.allclose(np.sort(h_naive), Z[:, 2], rtol=1e-9):
            nbad += 1
            print("ward heights differ", n)
        m_sc = rcast.scipy_to_r_merge(Z, n)
        cuts = kn.cut_tree_labels(Z, n, list(range(1, n + 1)))
        for q in range(1, n + 1):
            a = rcast.r_cutree(m_naive, q)
            b = rcast.r_cutree(m_sc, q)
            if not np.array_equal(a, b) or not np.array_equal(cuts[q] + 1, b):
                nbad += 1
                print("cutree differs", n, q)
                break
    print("ward.D2 naive vs scipy + R cutree vs cut_tree_labels: mismatching cases =", nbad, "of 25")

    # PC sign: partition invariant (flip the sign in the re-derivation)
    flips = 0
    for kind, s, pred, k, maxp, nk_len in cases[:30]:
        try:
            a = rcast.knndm_geo(s, pred, k, maxp, nk_len, R=R, rand=kn.random_folds(len(s), k, 42) + 1, pc_sign=+1)
            b = rcast.knndm_geo(s, pred, k, maxp, nk_len, R=R, rand=kn.random_folds(len(s), k, 42) + 1, pc_sign=-1)
        except RuntimeError:
            continue
        if not (a["random"] or (a["q"] == b["q"] and rcast.same_partition(a["clust"], b["clust"]))):
            flips += 1
    print("PC sign flip changes the partition in", flips, "of 30 cases")


if __name__ == "__main__":
    main()
