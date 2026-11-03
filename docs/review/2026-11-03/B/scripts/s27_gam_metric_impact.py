"""Impact of the GAM numerical error on reported metrics (synthetic data of synthA): for every transfer setting of
transfer_matrix (pairwise from Asia/Europe/North America/South America; LOCO), the GAM's test-site predictions from
fit_gam vs from the null-space-exact penalised LS at the SAME selected alpha (same basis, same linear continuation);
reports max |prediction difference| and the r2 difference per row."""
import sys, warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from statsmodels.gam.api import BSplines
from mshi.config import load_config
from mshi.analysis import transfer as T
warnings.simplefilter("ignore")
cfg = load_config(); spec = T.Spec.from_cfg(cfg); g = spec.gam
d = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet").sort_values("site_id").reset_index(drop=True)
conts = cfg["phase2"]["continents"]

def ref_predictor(tr, alpha):
    X = T.design(tr, g["features"], g["log"]); y = tr[spec.target].to_numpy(float)
    bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
    Xd = np.hstack([np.ones((len(X), 1)), bs.basis]); p = Xd.shape[1]
    V = np.zeros((p, p)); lam = np.zeros(p); V[0, 0] = 1.0; o = 1
    for a, sm in zip(alpha, bs.smoothers):
        k = sm.dim_basis; w, U = np.linalg.eigh(sm.cov_der2); w = np.where(w < 1e-9 * w.max(), 0.0, w)
        V[o:o + k, o:o + k] = U; lam[o:o + k] = 2 * a * w; o += k
    Z = Xd @ V; beta = V @ np.linalg.solve(Z.T @ Z + np.diag(lam), Z.T @ y)
    def predict(df):
        Xn = T.design(df, g["features"], g["log"])
        B = np.hstack([T.spline_basis(s, Xn[:, j]) for j, s in enumerate(bs.smoothers)])
        return beta[0] + B @ beta[1:]
    return predict

out = []
for table, label, trc, tests in T._settings(conts):
    tr = d[d.continent_geo.isin(trc)]
    if len(tr) < cfg["phase2"]["min_test_sites"]:
        continue
    m = T.fit_gam(spec, tr); rp = ref_predictor(tr, np.array(m.info["alpha"]))
    for c in tests:
        te = d[d.continent_geo == c]
        y = te.log_rs.to_numpy(); a, b = m.predict(te), rp(te)
        out.append((table, label, c, np.max(np.abs(a - b)), T.r2(y, a) - T.r2(y, b), m.info["alpha"]))
out.sort(key=lambda r: -r[3])
print("largest differences (table, train, test, max|dpred|, r2(fit_gam) - r2(exact), alpha):")
for r in out[:8]:
    print(f"  {r[0]:8s} {r[1]:14s} {r[2]:14s} {r[3]:.2e} {r[4]:+.2e} {['%.1e' % v for v in r[5]]}")
print("rows:", len(out), " max |r2 difference|:", max(abs(r[4]) for r in out))
