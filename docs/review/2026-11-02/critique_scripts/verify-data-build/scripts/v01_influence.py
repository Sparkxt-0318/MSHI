"""Independent estimate of the influence of the 2 French Guiana + 2 Tenerife 'Europe' sites on the locked OLS-TP R2.
Analytic leave-out using locked JSON (n, R2) + E6 RMSE(log) to get SSE/SST; y from rebuilt v3 QC site table;
predictions at the removed sites from two independent Asia OLS-TP approximations and a grid of plausible WorldClim values."""
import json, sys, itertools, numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import BallTree
from sklearn.metrics import r2_score
V = sys.argv[1]; H = "/home/user/MSHI/docs/handoff/results"
P = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed"
st = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet"); rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
srdb = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
L = json.load(open(f"{H}/clean_test_europe.json"))["primary"]; e6 = json.load(open(f"{H}/E6_matrix_OLS-TP.json"))["pairwise"]["Asia -> Europe"]
n, r2 = L["n"], L["r2"]
for rmse in (0.5345, 0.535, 0.5355):   # E6 RMSE is rounded to 3 dp
    SSE = n * rmse ** 2; SST = SSE / (1 - r2); print(f"rmse={rmse}: SSE={SSE:.3f} SST={SST:.3f} var_y={SST/n:.4f}")
SSE = n * 0.535 ** 2; SST = SSE / (1 - r2)
E = st[st.continent == "Europe"]; print("rebuilt Europe 236 sites var(y, ddof0) =", round(E.log_rs.var(ddof=0), 4), " mean", round(E.log_rs.mean(), 4))
ybar = E.log_rs.mean()
# --- Asia model (a): WorldClim borrowed from the nearest original repo site within 10 km
rep = pd.concat([pd.read_parquet(f"{P}/training_features_v2.parquet"), pd.read_parquet(f"{P}/us_validation_features_v2.parquet")]).dropna(subset=["bio01", "bio12"])
tree = BallTree(np.radians(rep[["latitude", "longitude"]].values), metric="haversine")
A = st[st.continent == "Asia"].copy(); d, i = tree.query(np.radians(A[["lat", "lon"]].values), k=1)
A["bio01"], A["bio12"] = rep.bio01.values[i[:, 0]], rep.bio12.values[i[:, 0]]; Aa = A[d[:, 0] * 6371 <= 10]
ma = LinearRegression().fit(np.c_[Aa.bio01, np.log(Aa.bio12)], Aa.log_rs)
# --- Asia model (b): SRDB-reported MAT/MAP averaged over each site's QC records (sites without MAT/MAP dropped)
base = rec[~rec.f_offland & ~rec.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].copy()
qc["row"] = qc.rec_id.str.extract(r"srdb_(\d+)$")[0].astype(float)
qc = qc.join(srdb[["MAT", "MAP"]], on="row")
# map record -> site by nearest site centroid within the same continent (sites are 5-km components; centroid within the component)
stree = BallTree(np.radians(st[["lat", "lon"]].values), metric="haversine")
_, si = stree.query(np.radians(qc[["lat", "lon"]].values), k=1); qc["site_id"] = st.site_id.values[si[:, 0]]
clim = qc.groupby("site_id")[["MAT", "MAP"]].mean()
Ab = A.drop(columns=["bio01", "bio12"]).join(clim, on="site_id").dropna(subset=["MAT", "MAP"]); Ab = Ab[Ab.MAP > 0]
mb = LinearRegression().fit(np.c_[Ab.MAT, np.log(Ab.MAP)], Ab.log_rs)
for nm, m, nn in [("a borrowed-WorldClim", ma, len(Aa)), ("b SRDB MAT/MAP", mb, len(Ab))]:
    print(f"Asia model ({nm}) n={nn}: a={m.intercept_:.3f} bT={m.coef_[0]:.4f} blnP={m.coef_[1]:.4f}")
fg = E[(E.lat < 10)]; can = E[(E.lat > 25) & (E.lat < 30) & (E.lon < -10)]
print("FG y:", fg.log_rs.round(3).tolist(), " Canary y:", can.log_rs.round(3).tolist())
def leave_out(y, p):
    y, p = np.asarray(y), np.asarray(p); n2 = n - len(y); ybar2 = (n * ybar - y.sum()) / n2
    SST2 = SST - ((y - ybar) ** 2).sum() - n2 * (ybar2 - ybar) ** 2; SSE2 = SSE - ((y - p) ** 2).sum()
    return 1 - SSE2 / SST2
res = []
for nm, m in [("a", ma), ("b", mb)]:
    for T, Pm in itertools.product([25.5, 26.0, 26.5, 27.0], [2200, 2600, 3000, 3200]):
        p = m.predict(np.c_[[T, T], np.log([Pm, Pm])]); res.append((nm, T, Pm, p[0], leave_out(fg.log_rs, p)))
r = pd.DataFrame(res, columns=["model", "T", "P", "pred", "R2_noFG"])
print(r.groupby("model").agg(pred_min=("pred", "min"), pred_max=("pred", "max"), R2_min=("R2_noFG", "min"), R2_max=("R2_noFG", "max")).round(3))
# Canaries: SRDB MAT/MAP 12.6/695 and 10.7/368 ; also a wider plausible range
for nm, m in [("a", ma), ("b", mb)]:
    pc = m.predict(np.c_[[12.6, 10.7], np.log([695, 368])]); pf = m.predict(np.c_[[26.0, 26.0], np.log([3000, 3000])])
    print(f"model {nm}: canary preds {pc.round(3)}; R2 without FG+Canaries = {leave_out(np.r_[fg.log_rs, can.log_rs], np.r_[pf, pc]):.3f}")
# break-even: residual sum of squares at FG needed for no change in R2
yv = fg.log_rs.values; n2 = n - 2; ybar2 = (n * ybar - yv.sum()) / n2
dSST = ((yv - ybar) ** 2).sum() + n2 * (ybar2 - ybar) ** 2
print(f"SST drop from removing FG = {dSST:.3f} ({dSST/SST:.1%} of SST); FG residual SS needed for R2 to be unchanged = {(1-r2)*dSST:.3f}")
print(f"If FG were predicted perfectly: R2_noFG = {leave_out(yv, yv):.3f}; if predicted at the Europe mean prediction (ybar-0.046): {leave_out(yv, [ybar-0.046]*2):.3f}")
