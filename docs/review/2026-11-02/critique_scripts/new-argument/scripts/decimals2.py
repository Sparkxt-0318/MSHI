import sys, numpy as np, pandas as pd
from statsmodels.stats.proportion import proportion_confint
REC, SRDB = sys.argv[1:3]
m = pd.read_parquet(sys.argv[3])
raw = pd.read_csv(SRDB, dtype=str, usecols=["Latitude", "Longitude"], keep_default_na=False)
F = (m.ptype == "Forest") & (m.min_ndec >= 4)
k = int((m[F].pixel == "Forest").sum()); n = int(F.sum())
print(f">=4-dec forest plots: {k}/{n} = {k/n:.3f}, Wilson 95% CI {np.round(proportion_confint(k, n, method='wilson'), 3)}")
k2 = int((m[m.ptype == 'Forest'].pixel == 'Forest').sum()); n2 = int((m.ptype == 'Forest').sum())
print(f"all forest plots: {k2}/{n2} = {k2/n2:.3f}, Wilson {np.round(proportion_confint(k2, n2, method='wilson'), 3)}")
# minute-level vs second-level DMS at >=4 decimals among all SRDB records with >=4 decimals in both coords
def nd(x): return x.str.split(".").str[1].fillna("").str.len()
la, lo = raw.Latitude, raw.Longitude
ok = (la != "") & (lo != "")
la, lo = la[ok], lo[ok]
four = (np.minimum(nd(la), nd(lo)) >= 4)
fa, fo = la.astype(float).abs(), lo.astype(float).abs()
minute = (np.abs(fa*60 - np.round(fa*60)) < 0.006) & (np.abs(fo*60 - np.round(fo*60)) < 0.006)
second = (np.abs(fa*3600 - np.round(fa*3600)) < 0.06) & (np.abs(fo*3600 - np.round(fo*3600)) < 0.06)
print(f"SRDB rows with >=4 dec in both coords: {int(four.sum())}; minute-level DMS: {int((four & minute).sum())}; second-level (not minute): {int((four & second & ~minute).sum())}")
# random expectation of 'minute' test passing at >=4 decimals for a random 4-6 decimal value: approx (0.012)^2 -> tiny
ex = la[four & minute].head(8).tolist(); print("examples minute-level:", list(zip(ex, lo[four & minute].head(8).tolist())))
