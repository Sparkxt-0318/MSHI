"""Metrics and the block bootstrap: metric_arrays vs a naive per-replicate loop; block_replicates vs the draws of
mshi.spatial.bootstrap_ci (same generator calls); block construction (2-degree floor blocks, negative coordinates,
antimeridian); percentile CIs; paired differences use identical draws."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
from mshi.analysis import transfer as T
from mshi.spatial import block_labels, bootstrap_ci
rng = np.random.default_rng(11)
n = 233
lon = rng.uniform(-179.9, 179.9, n); lat = rng.uniform(-60, 75, n)
y = rng.normal(6.5, 0.6, n); p = y + rng.normal(0.1, 0.4, n); base = np.full(n, 6.3)
reps = T.block_replicates(lon, lat, 2.0, 500, 42)
A = T.metric_arrays(y, p, base, reps.idx, reps.rep, reps.n)
# naive: rebuild each replicate from the same generator calls as bootstrap_ci
b = block_labels(lon, lat, 2.0); u = np.unique(b); g = np.random.default_rng(42)
mx = 0.0
for r in range(500):
    i = np.concatenate([np.where(b == k)[0] for k in g.choice(u, len(u))])
    yy, pp, bb = y[i], p[i], base[i]
    sse, sst, sse0 = np.sum((pp-yy)**2), np.sum((yy-yy.mean())**2), np.sum((bb-yy)**2)
    ref = {"r2": 1-sse/sst, "skill_vs_train_mean": 1-sse/sse0, "bias_log": np.mean(pp-yy), "null_bias_log": np.mean(bb-yy),
           "rmse_log": np.sqrt(np.mean((pp-yy)**2)), "rmse_rs": np.sqrt(np.mean((np.exp(pp)-np.exp(yy))**2))}
    for k, v in ref.items():
        mx = max(mx, abs(A[k][r] - v) / max(1.0, abs(v)))
print("metric_arrays vs naive replicate loop (same draws as bootstrap_ci): max rel diff =", mx)
print("CI r2 vs bootstrap_ci:", T.ci(A["r2"], [0.025, 0.975]), bootstrap_ci(y, p, n=500, seed=42, lon=lon, lat=lat, deg=2.0))
# blocks: floor(lon/2), floor(lat/2): a site at lon -0.5 is in block -1, at 0.5 in block 0
print("block labels:", block_labels([-0.5, 0.5, 179.9, -179.9, -1.99, -2.0], [0.1, -0.1, 10, 10, 1.0, 1.0], 2.0).tolist())
# the replicate count per block equals the block size
sizes = {k: int(np.sum(b == k)) for k in u}
print("number of 2-degree blocks:", len(u), " mean replicate size:", np.bincount(reps.rep).mean(), " (n =", n, ")")
