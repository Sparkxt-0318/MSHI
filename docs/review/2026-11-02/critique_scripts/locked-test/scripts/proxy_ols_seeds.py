"""PROXY ONLY: stability of the fixed-model vs Asia-refit CI lower bound across bootstrap seeds; also 2-deg blocks + refit."""
import sys
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
W = sys.argv[1]
a = pd.read_parquet(f"{W}/out/asia_384_proxy.parquet").dropna(subset=["mat", "map"]).reset_index(drop=True)
e = pd.read_parquet(f"{W}/out/europe_235_proxy.parquet").dropna(subset=["mat", "map"]).reset_index(drop=True)
Xa, Xe = np.c_[a["mat"], np.log(a["map"])], np.c_[e["mat"], np.log(e["map"])]; ya, ye = a.log_rs.values, e.log_rs.values
p = LinearRegression().fit(Xa, ya).predict(Xe)
b = (np.floor(e.lon / 2).astype(int).astype(str) + "_" + np.floor(e.lat / 2).astype(int).astype(str)).values
u = np.unique(b); idx = {k: np.where(b == k)[0] for k in u}
for seed in (1, 2, 3):
    rng = np.random.default_rng(seed); f, t, fb, tb = [], [], [], []
    for _ in range(2000):
        i = rng.integers(0, len(ye), len(ye)); j = rng.integers(0, len(ya), len(ya))
        pj = LinearRegression().fit(Xa[j], ya[j]).predict(Xe)
        f.append(r2_score(ye[i], p[i])); t.append(r2_score(ye[i], pj[i]))
        k = np.concatenate([idx[x] for x in rng.choice(u, len(u))]); fb.append(r2_score(ye[k], p[k])); tb.append(r2_score(ye[k], pj[k]))
    q = lambda v: round(float(np.quantile(v, .025)), 4)
    print(f"seed {seed}: site fixed {q(f)}  site+refit {q(t)}  shift {q(t)-q(f):+.4f} | block2 fixed {q(fb)}  block2+refit {q(tb)}  shift {q(tb)-q(fb):+.4f}")
