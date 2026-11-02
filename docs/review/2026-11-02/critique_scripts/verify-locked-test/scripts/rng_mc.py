"""RNG sensitivity of the 2.5% bootstrap bound (2,000 draws) for the exact Europe y (n=235) and synthetic
predictions with R2 ~0.079 and bias -0.046 (the real predictions are not available offline)."""
import numpy as np, pandas as pd
E = pd.read_parquet("out/europe_235.parquet"); y = E.log_rs.values; n = len(y)
def r2(y, p): return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)
# synthetic p: shrunken signal + noise, tuned so r2(y,p) ~ 0.079 and mean(p-y) = -0.046
g = np.random.default_rng(0); z = g.standard_normal(n)
best = None
for k in np.linspace(0.05, 0.6, 111):
    for s in np.linspace(0.0, 0.4, 81):
        p = y.mean() - 0.046 + k * (y - y.mean()) + s * (z - z.mean())
        v = r2(y, p)
        if best is None or abs(v - 0.079) < abs(best[0] - 0.079): best = (v, k, s)
v, k, s = best; p = y.mean() - 0.046 + k * (y - y.mean()) + s * (z - z.mean())
print("synthetic p: r2 %.4f bias %.4f k %.3f s %.3f" % (r2(y, p), np.mean(p - y), k, s))
b = (np.floor(E.lon.values / 2).astype(int).astype(str) + "_" + np.floor(E.lat.values / 2).astype(int).astype(str))
u = np.unique(b); idx = {kk: np.where(b == kk)[0] for kk in u}
lo_site, lo_blk = [], []
for seed in range(100):
    rng = np.random.default_rng(seed)
    bs = [r2(y[i], p[i]) for i in (rng.integers(0, n, n) for _ in range(2000))]; lo_site.append(np.quantile(bs, .025))
    rng = np.random.default_rng(seed); bb = []
    for _ in range(2000):
        i = np.concatenate([idx[kk] for kk in rng.choice(u, len(u))]); bb.append(r2(y[i], p[i]))
    lo_blk.append(np.quantile(bb, .025))
print("site 2.5%% bound: mean %.4f SD over 100 seeds %.4f" % (np.mean(lo_site), np.std(lo_site)))
print("block2 2.5%% bound: mean %.4f SD over 100 seeds %.4f" % (np.mean(lo_blk), np.std(lo_blk)))
