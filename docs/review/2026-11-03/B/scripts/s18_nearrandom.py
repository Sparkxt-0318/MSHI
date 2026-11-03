"""Docstring claim (knndm.py): when CAST's KS test rejects for sites drawn from the prediction domain itself, kNNDM
returns a near-random split (q close to n; W at most 1.5 times the random split's in 100 toy draws)."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
from mshi.analysis import knndm as kn
def sphere_box(rng, n, lon=(0.0, 30.0), lat=(35.0, 60.0)):
    s0, s1 = np.sin(np.radians(lat[0])), np.sin(np.radians(lat[1]))
    return np.c_[rng.uniform(*lon, n), np.degrees(np.arcsin(rng.uniform(s0, s1, n)))]
ratios, qs = [], []
for i in range(100):
    rng = np.random.default_rng(100 + i)
    pred = sphere_box(rng, 2000); sites = sphere_box(rng, 150)
    f, info = kn.knndm_folds(sites, pred, 5, 0.5, "hierarchical", 42)
    if not info["random_cv"]:
        ratios.append(info["W"] / info["W_random"]); qs.append(info["q"])
print(f"{len(ratios)} of 100 draws rejected; q/n min {min(qs)/150:.2f}; W/W_random max {max(ratios):.2f}, median {np.median(ratios):.2f}")
