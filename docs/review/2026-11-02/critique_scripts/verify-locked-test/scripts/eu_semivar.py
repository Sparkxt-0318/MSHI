"""Empirical semivariogram of Europe log Rs (exact 235 locked-test sites) and of PROXY-model residuals."""
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
E = pd.read_parquet("out/europe_235.parquet"); y = E.log_rs.values
la, lo = np.radians(E.lat.values), np.radians(E.lon.values)
dl = la[:, None] - la[None, :]; dn = lo[:, None] - lo[None, :]
h = 2 * 6371 * np.arcsin(np.sqrt(np.sin(dl / 2) ** 2 + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dn / 2) ** 2))
iu = np.triu_indices(len(y), 1); H = h[iu]
bins = [0, 25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2500, 5000]
def sv(v):
    g = 0.5 * (v[:, None] - v[None, :]) ** 2; G = g[iu]
    return [(f"{a}-{b}", int(((H >= a) & (H < b)).sum()), round(float(G[(H >= a) & (H < b)].mean()), 3)) for a, b in zip(bins[:-1], bins[1:]) if ((H >= a) & (H < b)).sum() > 0]
print("Europe log Rs var %.3f" % y.var()); print(sv(y))
A = pd.read_parquet("out/asia_384_proxy.parquet").dropna(subset=["MAT", "MAP"]); Ep = pd.read_parquet("out/europe_235_proxy.parquet")
m = LinearRegression().fit(np.c_[A.MAT, np.log(A.MAP)], A.log_rs)
ok = Ep[["MAT", "MAP"]].notna().all(axis=1).values
res = np.full(len(Ep), np.nan); res[ok] = Ep.log_rs.values[ok] - m.predict(np.c_[Ep.MAT[ok], np.log(Ep.MAP[ok])])
# restrict to pairs with residuals
y2 = res; mask = ~np.isnan(y2)
la2, lo2 = la[mask], lo[mask]; v = y2[mask]
dl = la2[:, None] - la2[None, :]; dn = lo2[:, None] - lo2[None, :]
h2 = 2 * 6371 * np.arcsin(np.sqrt(np.sin(dl / 2) ** 2 + np.cos(la2[:, None]) * np.cos(la2[None, :]) * np.sin(dn / 2) ** 2))
iu2 = np.triu_indices(len(v), 1); H2 = h2[iu2]; G2 = (0.5 * (v[:, None] - v[None, :]) ** 2)[iu2]
print("PROXY residual var %.3f (n %d)" % (v.var(), len(v)))
print([(f"{a}-{b}", int(((H2 >= a) & (H2 < b)).sum()), round(float(G2[(H2 >= a) & (H2 < b)].mean()), 3)) for a, b in zip(bins[:-1], bins[1:]) if ((H2 >= a) & (H2 < b)).sum() > 0])
