"""PROXY ONLY (SRDB-reported MAT/MAP instead of WorldClim bio01/bio12; subset of sites with both reported).
(a) how much a CI that also resamples the Asia training sites (refit each draw) widens vs the locked fixed-model site bootstrap;
(b) g C RMSE with naive exp() back-transform (as in clean_test.py L89-92) vs Duan smearing applied to model AND baseline."""
import sys, json
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
W = sys.argv[1]
a = pd.read_parquet(f"{W}/out/asia_384_proxy.parquet").dropna(subset=["mat", "map"]).reset_index(drop=True)
e = pd.read_parquet(f"{W}/out/europe_235_proxy.parquet").dropna(subset=["mat", "map"]).reset_index(drop=True)
Xa, Xe = np.c_[a["mat"], np.log(a["map"])], np.c_[e["mat"], np.log(e["map"])]; ya, ye = a.log_rs.values, e.log_rs.values
m = LinearRegression().fit(Xa, ya); p = m.predict(Xe)
out = dict(n_asia=len(a), n_eu=len(e), coef=[float(c) for c in m.coef_], r2_eu=float(r2_score(ye, p)), insample_r2_asia=float(m.score(Xa, ya)))
rng = np.random.default_rng(42); fixed, two = [], []
for _ in range(2000):
    i = rng.integers(0, len(ye), len(ye)); fixed.append(r2_score(ye[i], p[i]))
    j = rng.integers(0, len(ya), len(ya)); pj = LinearRegression().fit(Xa[j], ya[j]).predict(Xe)
    two.append(r2_score(ye[i], pj[i]))
q = lambda v: [round(float(np.quantile(v, .025)), 4), round(float(np.quantile(v, .975)), 4)]
out["ci_site_fixed_model"] = q(fixed); out["ci_site_plus_asia_refit"] = q(two)
out["lower_bound_shift"] = round(out["ci_site_plus_asia_refit"][0] - out["ci_site_fixed_model"][0], 4)
O = np.exp(ye); rm = lambda c: round(float(np.sqrt(np.mean((c - O) ** 2))), 1)
s_m = float(np.mean(np.exp(ya - m.predict(Xa)))); s_0 = float(np.mean(np.exp(ya - ya.mean())))
out["duan_smear_model"], out["duan_smear_intercept"] = round(s_m, 3), round(s_0, 3)
out["rmse_gC"] = {"model_naive": rm(np.exp(p)), "intercept_naive(geomean)": rm(np.exp(ya.mean())),
                  "model_smeared": rm(s_m * np.exp(p)), "intercept_smeared(=Asia arith. mean)": rm(s_0 * np.exp(ya.mean())),
                  "oracle_const_EU_mean": rm(O.mean())}
out["rmse_gC_rel_gain_naive"] = round(1 - out["rmse_gC"]["model_naive"] / out["rmse_gC"]["intercept_naive(geomean)"], 4)
out["rmse_gC_rel_gain_smeared"] = round(1 - out["rmse_gC"]["model_smeared"] / out["rmse_gC"]["intercept_smeared(=Asia arith. mean)"], 4)
print(json.dumps(out, indent=1))
