"""Identify which coastal Asia/Europe QC sites were dropped (missing WorldClim) by matching rmse_rs_intercept exactly."""
import sys, itertools
import numpy as np, pandas as pd
W = sys.argv[1]
s = pd.read_parquet(f"{W}/out/v3/sites_v3_qc.parquet")
A, E = s[s.continent == "Asia"], s[s.continent == "Europe"]
asia_c = ["v3qc_00184", "v3qc_00567", "v3qc_00576", "v3qc_00604", "v3qc_00872"]
eu_c = ["v3qc_00280", "v3qc_00283", "v3qc_00559", "v3qc_00765"]
TARGET = 386.9086311104987
best = []
for da in itertools.combinations(asia_c, 3):
    a = A[~A.site_id.isin(da)]
    for de in eu_c:
        e = E[E.site_id != de]
        r = float(np.sqrt(np.mean((np.exp(a.log_rs.mean()) - np.exp(e.log_rs.values)) ** 2)))
        best.append((abs(r - TARGET), r, da, de, len(a), len(e)))
best.sort()
for b in best[:5]: print(b)
a, e = A, E
print("all sites (387/236):", float(np.sqrt(np.mean((np.exp(a.log_rs.mean()) - np.exp(e.log_rs.values)) ** 2))))
