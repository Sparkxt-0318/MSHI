"""GAM accuracy: fit_gam's coefficients vs an independent penalized least-squares solution (QR of [X; R] with
R'R = 2 * blockdiag(alpha_j * cov_der2_j), the penalty statsmodels' PIRLS uses) at the alpha fit_gam selected, on the
training sets of the synthetic Europe kNNDM folds, the transfer training sets, and at forced extreme alphas
(1e20 .. 1e40) to show where statsmodels' pinv (rcond 1e-15) starts truncating the penalty's null space."""
import sys, copy, warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from statsmodels.gam.api import BSplines, GLMGam
from mshi.config import load_config
from mshi.analysis import transfer as T
warnings.simplefilter("ignore")
cfg = load_config(); spec = T.Spec.from_cfg(cfg); g = spec.gam
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet").sort_values("site_id").reset_index(drop=True)

def exact(train, alpha):
    X = T.design(train, g["features"], g["log"]); y = train[spec.target].to_numpy(float)
    bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
    Xd = np.hstack([np.ones((len(X), 1)), bs.basis])
    S = np.zeros((Xd.shape[1], Xd.shape[1])); o = 1
    for a, sm in zip(alpha, bs.smoothers):
        k = sm.dim_basis; S[o:o + k, o:o + k] = a * sm.cov_der2; o += k
    lam, V = np.linalg.eigh(2 * S); lam = np.clip(lam, 0, None)
    R = (np.sqrt(lam)[:, None] * V.T)
    A = np.vstack([Xd, R]); b = np.r_[y, np.zeros(len(R))]
    Q, Rq = np.linalg.qr(A)
    return np.linalg.solve(Rq, Q.T @ b), Xd, y, bs

sets = []
for c in ("Europe", "Asia", "North America"):
    sub = synth[synth.continent_geo == c].reset_index(drop=True)
    for s in (42,):
        from mshi.spatial import block_folds
        for tr, va in block_folds(sub.lon.values, sub.lat.values, s, 5.0, 5):
            sets.append((f"{c} blocks fold", sub.iloc[tr]))
for tr_c in ("Asia", "Europe", "North America", "South America"):
    sets.append((f"train {tr_c}", synth[synth.continent_geo == tr_c]))
worst = 0.0
for name, tr in sets:
    m = T.fit_gam(spec, tr)
    beta, Xd, y, bs = exact(tr, np.array(m.info["alpha"]))
    p_exact = Xd @ beta
    d = np.max(np.abs(m.predict(tr) - p_exact))
    worst = max(worst, d)
print(f"{len(sets)} training sets: max |fit_gam prediction - exact penalized LS| at the selected alpha = {worst:.2e}")
tr = synth[synth.continent_geo == "Europe"]
for la in (12, 16, 20, 25, 30, 35, 40):
    alpha = np.array([10.0 ** la, 10.0 ** la])
    X = T.design(tr, g["features"], g["log"]); yv = tr[spec.target].to_numpy(float)
    bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
    res = GLMGam(yv, exog=np.ones((len(X), 1)), smoother=bs, alpha=alpha).fit()
    beta, Xd, y, _ = exact(tr, alpha)
    lin = np.linalg.lstsq(np.c_[np.ones(len(X)), X], yv, rcond=None)[0]
    p_lin = np.c_[np.ones(len(X)), X] @ lin
    print(f"alpha=1e{la}: max|statsmodels - exact| = {np.max(np.abs(res.fittedvalues - Xd @ beta)):.2e}; "
          f"max|exact - linear limit| = {np.max(np.abs(Xd @ beta - p_lin)):.2e}; edf={np.sum(res.edf):.2f}; aic={res.aic:.2f}")
