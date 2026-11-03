"""GAM numerical accuracy with a null-space-exact reference. Penalised LS: minimise ||y - X b||^2 + b' (2 S_alpha) b,
S_alpha = blockdiag(0, alpha_1 C_1, alpha_2 C_2) (statsmodels' cov_der2 C_j; PIRLS augments with 2*S). Reference: in the
eigenbasis of each C_j (unscaled), eigenvalues below 1e-9 * max are set to exactly 0 (the second-derivative null space:
the linear trend), then the normal equations in that basis are solved (diagonally dominant in the penalised block).
Checks: the reference tends to OLS on (1, bio01, ln bio12) as alpha -> inf; statsmodels' GLMGam fit (as fit_gam uses
it) vs the reference over alpha; and fit_gam (selected alpha) vs the reference on many training sets."""
import sys, warnings
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from statsmodels.gam.api import BSplines, GLMGam
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.spatial import block_folds
warnings.simplefilter("ignore")
cfg = load_config(); spec = T.Spec.from_cfg(cfg); g = spec.gam
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet").sort_values("site_id").reset_index(drop=True)

def basis(tr):
    X = T.design(tr, g["features"], g["log"]); y = tr[spec.target].to_numpy(float)
    bs = BSplines(X, df=[g["df"]] * 2, degree=[g["degree"]] * 2)
    return X, y, bs

def reference(X, y, bs, alpha):
    Xd = np.hstack([np.ones((len(X), 1)), bs.basis])
    p = Xd.shape[1]; V = np.zeros((p, p)); lam = np.zeros(p); V[0, 0] = 1.0; o = 1
    for a, sm in zip(alpha, bs.smoothers):
        k = sm.dim_basis; w, U = np.linalg.eigh(sm.cov_der2)
        w = np.where(w < 1e-9 * w.max(), 0.0, w)
        V[o:o + k, o:o + k] = U; lam[o:o + k] = 2 * a * w; o += k
    Z = Xd @ V
    gam = np.linalg.solve(Z.T @ Z + np.diag(lam), Z.T @ y)
    return Xd @ (V @ gam)

tr = synth[synth.continent_geo == "Europe"]
X, y, bs = basis(tr)
ols = np.c_[np.ones(len(X)), X] @ np.linalg.lstsq(np.c_[np.ones(len(X)), X], y, rcond=None)[0]
print("alpha        max|ref - OLS(1,bio01,ln bio12)|   max|statsmodels - ref|   statsmodels edf   statsmodels aic")
for la in (0, 4, 8, 10, 12, 13, 14, 15, 16, 18, 20):
    al = np.array([10.0 ** la] * 2)
    ref = reference(X, y, bs, al)
    res = GLMGam(y, exog=np.ones((len(X), 1)), smoother=bs, alpha=al).fit()
    print(f"1e{la:<4d}      {np.max(np.abs(ref - ols)):.2e}                        {np.max(np.abs(res.fittedvalues - ref)):.2e}"
          f"               {np.sum(res.edf):5.2f}             {res.aic:8.2f}")
# fit_gam at its selected alpha vs the reference, many training sets
rows = []
for c in ("Europe", "Asia", "North America"):
    sub = synth[synth.continent_geo == c].reset_index(drop=True)
    for s in (42, 43, 44):
        for k, (trn, va) in enumerate(block_folds(sub.lon.values, sub.lat.values, s, 5.0, 5)):
            rows.append((f"{c} seed {s} fold {k}", sub.iloc[trn]))
for tr_c in ("Asia", "Europe", "North America", "South America"):
    rows.append((f"transfer train {tr_c}", synth[synth.continent_geo == tr_c]))
bad = []
for name, trn in rows:
    m = T.fit_gam(spec, trn)
    X, y, bs = basis(trn)
    d = np.max(np.abs(m.predict(trn) - reference(X, y, bs, np.array(m.info["alpha"]))))
    bad.append((d, name, m.info["alpha"], m.info["edf"], m.info["aic"]))
bad.sort(reverse=True)
print(f"\n{len(rows)} training sets; fit_gam vs reference at the selected alpha, largest differences:")
for d, name, a, edf, aic in bad[:8]:
    print(f"  {d:.2e}  {name:32s} alpha={['%.1e' % v for v in a]} edf={edf:.2f} aic={aic:.2f}")
print("sets with max |difference| > 1e-3:", sum(d > 1e-3 for d, *_ in bad), "; > 1e-2:", sum(d > 1e-2 for d, *_ in bad))
