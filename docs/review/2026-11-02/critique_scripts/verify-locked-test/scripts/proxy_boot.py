"""PROXY test of the 'training-sample uncertainty' claim (finding locked-test-h1-ci-conditional) and the
back-transform claim (locked-test-gC-backtransform-baseline). Covariates: SRDB site-mean MAT and ln(MAP) in place
of WorldClim bio01/ln bio12 -> NOT the locked model; only the size of effects is of interest."""
import json, sys
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
A = pd.read_parquet("out/asia_384_proxy.parquet").dropna(subset=["MAT", "MAP"]).reset_index(drop=True)
E = pd.read_parquet("out/europe_235_proxy.parquet").dropna(subset=["MAT", "MAP"]).reset_index(drop=True)
D = lambda d: np.c_[d.MAT.values, np.log(d.MAP.values)]
Xa, ya, Xe, ye = D(A), A.log_rs.values, D(E), E.log_rs.values
m = LinearRegression().fit(Xa, ya); p = m.predict(Xe)
def blk(lon, lat, deg): return (np.floor(lon / deg).astype(int).astype(str) + "_" + np.floor(lat / deg).astype(int).astype(str))
def boot_ci(y, p, lon=None, lat=None, deg=None, n=2000, seed=42):   # verbatim logic of clean_test.py L68-77
    rng = np.random.default_rng(seed)
    if deg is None:
        bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    else:
        b = blk(lon, lat, deg); u = np.unique(b); idx = {k: np.where(b == k)[0] for k in u}; bs = []
        for _ in range(n):
            i = np.concatenate([idx[k] for k in rng.choice(u, len(u))]); bs.append(r2_score(y[i], p[i]))
    return [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]
def two_sample(deg_e=None, n=2000, seed=42, asia_deg=None):
    rng = np.random.default_rng(seed); bs = []
    be = blk(E.lon.values, E.lat.values, deg_e) if deg_e else None
    ue = np.unique(be) if deg_e else None; ide = {k: np.where(be == k)[0] for k in ue} if deg_e else None
    ba = blk(A.lon.values, A.lat.values, asia_deg) if asia_deg else None
    ua = np.unique(ba) if asia_deg else None; ida = {k: np.where(ba == k)[0] for k in ua} if asia_deg else None
    for _ in range(n):
        ia = np.concatenate([ida[k] for k in rng.choice(ua, len(ua))]) if asia_deg else rng.integers(0, len(ya), len(ya))
        mm = LinearRegression().fit(Xa[ia], ya[ia])
        ie = np.concatenate([ide[k] for k in rng.choice(ue, len(ue))]) if deg_e else rng.integers(0, len(ye), len(ye))
        bs.append(r2_score(ye[ie], mm.predict(Xe[ie])))
    return [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))], float(np.median(bs))
R = dict(n_asia=len(A), n_eu=len(E), coef=m.coef_.tolist(), r2_in_asia=float(m.score(Xa, ya)), r2_eu=float(r2_score(ye, p)),
         bias_log=float(np.mean(p - ye)))
for seed in (42, 1, 2, 3):
    fs = boot_ci(ye, p, seed=seed); fb = boot_ci(ye, p, E.lon.values, E.lat.values, 2.0, seed=seed)
    ts, tsm = two_sample(seed=seed); tb, tbm = two_sample(deg_e=2.0, seed=seed)
    R[f"seed{seed}"] = dict(fixed_site=fs, two_sample_site=ts, drop_site=fs[0] - ts[0],
                            fixed_block2=fb, two_sample_block2=tb, drop_block2=fb[0] - tb[0], median_two_sample_site=tsm)
# also Asia resampled by 5-degree blocks (spatial training-sample uncertainty) + Europe 2-degree blocks
tb5, _ = two_sample(deg_e=2.0, seed=42, asia_deg=5.0); R["two_sample_asia5_eu2"] = tb5
# --- back-transform (Duan smearing) on the proxy
ro = np.exp(ye); smear_m = float(np.mean(np.exp(ya - m.predict(Xa)))); smear_0 = float(np.mean(np.exp(ya - ya.mean())))
rm = lambda q: float(np.sqrt(np.mean((q - ro) ** 2)))
R["gC"] = dict(model_naive=rm(np.exp(p)), base_naive=rm(np.exp(ya.mean())), model_smeared=rm(smear_m * np.exp(p)),
               base_smeared=rm(smear_0 * np.exp(ya.mean())), smear_model=smear_m, smear_base=smear_0, oracle=rm(ro.mean()))
R["gC"]["gain_naive"] = 1 - R["gC"]["model_naive"] / R["gC"]["base_naive"]; R["gC"]["gain_smeared"] = 1 - R["gC"]["model_smeared"] / R["gC"]["base_smeared"]
print(json.dumps(R, indent=1))
