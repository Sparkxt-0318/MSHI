"""Influence of the two French Guiana 'Europe' sites (and two Canary sites) on the locked Asia->Europe OLS-TP R2.
Asia OLS-TP is refit on rebuilt v3 Asia QC sites with WorldClim bio01/bio12 borrowed from the nearest original repo
site (<=10 km). Europe values: (i) analytic leave-out using the locked JSON's SSE/SST, (ii) SRDB-reported MAT/MAP proxy."""
import sys, json, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import BallTree
from sklearn.metrics import r2_score
V3, PROC, SRDB, LOCKED, E6 = sys.argv[1:6]
st = pd.read_parquet(f"{V3}/sites_v3_qc.parquet")
rep = pd.concat([pd.read_parquet(f"{PROC}/training_features_v2.parquet"), pd.read_parquet(f"{PROC}/us_validation_features_v2.parquet")]).dropna(subset=["bio01", "bio12"])
tree = BallTree(np.radians(rep[["latitude", "longitude"]].values), metric="haversine")
A = st[st.continent == "Asia"].copy()
d, i = tree.query(np.radians(A[["lat", "lon"]].values), k=1)
A["bio01"], A["bio12"] = rep.bio01.values[i[:, 0]], rep.bio12.values[i[:, 0]]; A = A[d[:, 0] * 6371 <= 10]
m = LinearRegression().fit(np.c_[A.bio01, np.log(A.bio12)], A.log_rs)
print(f"Asia OLS-TP (borrowed WorldClim) n={len(A)}: b_T={m.coef_[0]:.4f} b_lnP={m.coef_[1]:.4f} a={m.intercept_:.3f}")
# French Guiana climate from SRDB-reported MAT/MAP of the records in those sites
s = pd.read_csv(SRDB, low_memory=False)
fg = {"v3qc_00091": "srdb_910", "v3qc_00185": "srdb_2075"}
L = json.load(open(LOCKED))["primary"]; e6 = json.load(open(E6))["pairwise"]["Asia -> Europe"]
n, r2, rmse = L["n"], L["r2"], e6["rmse"]
SSE = n * rmse ** 2; SST = SSE / (1 - r2)
E = st[st.continent == "Europe"]; ybar = E.log_rs.mean()
rows = []
for sid, rec in fg.items():
    x = s.loc[int(rec[5:])]; y = float(E.set_index("site_id").log_rs[sid])
    p = float(m.predict([[x.MAT, np.log(x.MAP)]])[0]); rows.append((sid, x.MAT, x.MAP, y, p))
    print(f"  {sid}: MAT={x.MAT} MAP={x.MAP} y={y:.3f} pred={p:.3f} resid={y-p:+.3f}  (Europe mean y {ybar:.3f})")
y = np.array([r[3] for r in rows]); p = np.array([r[4] for r in rows])
n2 = n - len(y); ybar2 = (n * ybar - y.sum()) / n2
SST2 = SST - ((y - ybar) ** 2).sum() - n2 * (ybar2 - ybar) ** 2
SSE2 = SSE - ((y - p) ** 2).sum()
print(f"locked: n={n} R2={r2:.3f} (SSE={SSE:.2f}, SST={SST:.2f}); analytic leave-out of 2 French Guiana sites: n={n2} R2={1-SSE2/SST2:.3f}")
