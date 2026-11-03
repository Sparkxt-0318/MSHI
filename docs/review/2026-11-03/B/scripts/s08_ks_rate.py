"""Documentation claim (knndm.py docstring, D-P2-7): with 150 sites drawn at random from the prediction domain's
distribution, CAST's KS test rejects in about 14% of 400 toy draws (0.5% with the duplicated LOO distances removed)."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
from mshi.analysis import knndm as kn
def sphere_box(rng, n, lon=(0.0, 30.0), lat=(35.0, 60.0)):
    s0, s1 = np.sin(np.radians(lat[0])), np.sin(np.radians(lat[1]))
    return np.c_[rng.uniform(*lon, n), np.degrees(np.arcsin(rng.uniform(s0, s1, n)))]
rej = rej_u = 0
for i in range(400):
    rng = np.random.default_rng(1000 + i)
    pred = sphere_box(rng, 2000); sites = sphere_box(rng, 150)
    gij = kn.nearest_km(sites, pred); gj = kn.nearest_km(sites)
    rej += kn.ks_greater(gj, gij)[1] < 0.05
    rej_u += kn.ks_greater(np.unique(gj), gij)[1] < 0.05
print(f"rejection rate {rej/400:.3f} (duplicates removed: {rej_u/400:.4f})")
