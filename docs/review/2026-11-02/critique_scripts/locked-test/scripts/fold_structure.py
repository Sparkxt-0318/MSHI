"""Asia selection-CV fold structure for the exact OLS-TP/C8 rows (384 Asia QC sites); folds() copied from clean_test.py L36-40."""
import sys, json
import numpy as np, pandas as pd
from sklearn.metrics import r2_score
W = sys.argv[1]
a = pd.read_parquet(f"{W}/out/asia_384.parquet")
def folds(df, seed, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); rng = np.random.default_rng(seed); rng.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]
y = a.log_rs.values
b = (np.floor(a.lon / 5).astype(int).astype(str) + "_" + np.floor(a.lat / 5).astype(int).astype(str)).values
u, c = np.unique(b, return_counts=True)
out = dict(n=len(a), n_blocks=int(len(u)), singleton_blocks=int((c == 1).sum()), sites_in_singletons=int((c == 1).sum()),
           largest_block=int(c.max()), top5_blocks=sorted(c.tolist(), reverse=True)[:5])
null_fold, null_pooled = [], []
for seed in (42, 43, 44):
    sizes, vars_, r2n = [], [], []
    p = np.empty(len(y))
    for tr, va in folds(a, seed):
        sizes.append(len(va)); vars_.append(round(float(y[va].var()), 3))
        r2n.append(r2_score(y[va], np.full(len(va), y[tr].mean()))); p[va] = y[tr].mean()
    null_fold += r2n; null_pooled.append(r2_score(y, p))
    out[f"seed{seed}"] = dict(fold_sizes=sizes, fold_var_logrs=vars_, null_r2_per_fold=[round(float(x), 3) for x in r2n])
out["null_model_mean_per_fold_r2_15folds"] = round(float(np.mean(null_fold)), 4)
out["null_model_pooled_oof_r2_by_seed"] = [round(float(x), 4) for x in null_pooled]
# probability that dropping k random sites removes >=1 singleton block (changes the block list -> new partition)
rng = np.random.default_rng(0); sing = set(u[c == 1])
for k in (1, 2, 4, 5):
    hits = np.mean([any(b[i] in sing for i in rng.choice(len(a), k, replace=False)) for _ in range(20000)])
    out[f"P(partition changes | drop {k} random sites)"] = round(float(hits), 3)
print(json.dumps(out, indent=1))
