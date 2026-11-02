"""Proxy re-score of Asia->Europe OLS-TP with SRDB-reported MAT/MAP (WorldClim unavailable) to see how the site-bootstrap
CI moves when the French Guiana / Canary 'Europe' sites are removed. Same bootstrap as clean_test.boot_ci (seed 42, 2000)."""
import sys, numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.neighbors import BallTree
V = sys.argv[1]
st = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet"); rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet")
srdb = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
base = rec[~rec.f_offland & ~rec.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].copy()
qc["row"] = qc.rec_id.str.extract(r"srdb_(\d+)$")[0].astype(float); qc = qc.join(srdb[["MAT", "MAP"]], on="row")
_, si = BallTree(np.radians(st[["lat", "lon"]].values), metric="haversine").query(np.radians(qc[["lat", "lon"]].values), k=1)
qc["site_id"] = st.site_id.values[si[:, 0]]
s2 = st.join(qc.groupby("site_id")[["MAT", "MAP"]].mean(), on="site_id").dropna(subset=["MAT", "MAP"]); s2 = s2[s2.MAP > 0]
A, E = s2[s2.continent == "Asia"], s2[s2.continent == "Europe"].copy()
m = LinearRegression().fit(np.c_[A.MAT, np.log(A.MAP)], A.log_rs); E["p"] = m.predict(np.c_[E.MAT, np.log(E.MAP)])
def boot(y, p, n=2000, seed=42):
    rng = np.random.default_rng(seed); bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    return np.quantile(bs, .025), np.quantile(bs, .975)
fg = (E.lat < 10); can = (E.lat < 30) & (E.lon < -10)
for tag, msk in [("as built", np.ones(len(E), bool)), ("minus French Guiana", ~fg.values), ("minus FG + Canaries", ~(fg | can).values)]:
    y, p = E.log_rs.values[msk], E.p.values[msk]; lo, hi = boot(y, p)
    print(f"{tag:22s} n={msk.sum():3d} R2={r2_score(y, p):.3f} CI [{lo:.3f}, {hi:.3f}]")
print("FG sites in proxy set:", int(fg.sum()), " Canary sites:", int(can.sum()))
