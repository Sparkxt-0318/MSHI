"""RNG sensitivity of the 2.5% bootstrap bound, synthetic predictions calibrated to the REAL locked result
(R2 0.079, bias -0.046, site CI ~[0.013, 0.125] at seed 42) on the exact Europe y (n=235)."""
import numpy as np, pandas as pd
E = pd.read_parquet("out/europe_235.parquet"); y = E.log_rs.values; n = len(y)
def r2(y, p): return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)
zy = (y - y.mean()) / y.std()
b = (np.floor(E.lon.values / 2).astype(int).astype(str) + "_" + np.floor(E.lat.values / 2).astype(int).astype(str))
u = np.unique(b); idx = {kk: np.where(b == kk)[0] for kk in u}
def site_boot(p, seed, B=2000):
    rng = np.random.default_rng(seed); return [r2(y[i], p[i]) for i in (rng.integers(0, n, n) for _ in range(B))]
def blk_boot(p, seed, B=2000):
    rng = np.random.default_rng(seed); out = []
    for _ in range(B):
        i = np.concatenate([idx[kk] for kk in rng.choice(u, len(u))]); out.append(r2(y[i], p[i]))
    return out
res = []
for zseed in range(6):
    z = np.random.default_rng(100 + zseed).standard_normal(n); z = (z - z.mean()) / z.std()
    z = z - np.dot(z, zy) / n * zy; z /= z.std()        # orthogonal to y
    for sp in (0.12, 0.15, 0.18, 0.22):
        # choose r so that R2 = 0.079 exactly given sp and bias
        for r in np.linspace(0.15, 0.6, 451):
            p = y.mean() - 0.046 + sp * (r * zy + np.sqrt(1 - r * r) * z)
            if r2(y, p) >= 0.079: break
        ci = np.quantile(site_boot(p, 42), [.025, .975])
        res.append((abs(ci[0] - 0.0134) + abs(ci[1] - 0.1254), zseed, sp, r, ci, p))
res.sort(key=lambda t: t[0]); _, zseed, sp, r, ci, p = res[0]
print("best calibration: pred SD %.2f, corr %.3f, R2 %.4f, bias %.4f, site CI seed42 [%.4f, %.4f], block CI seed42 %s" %
      (sp, r, r2(y, p), np.mean(p - y), ci[0], ci[1], np.round(np.quantile(blk_boot(p, 42), [.025, .975]), 4)))
lo_s = [np.quantile(site_boot(p, s), .025) for s in range(100)]
lo_b = [np.quantile(blk_boot(p, s), .025) for s in range(100)]
print("site lower bound over 100 RNG seeds: mean %.4f SD %.4f min %.4f max %.4f" % (np.mean(lo_s), np.std(lo_s), np.min(lo_s), np.max(lo_s)))
print("block2 lower bound over 100 RNG seeds: mean %.4f SD %.4f min %.4f max %.4f frac<0 %.2f" % (np.mean(lo_b), np.std(lo_b), np.min(lo_b), np.max(lo_b), np.mean(np.array(lo_b) < 0)))
