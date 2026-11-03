"""Shared helpers for the B-1 verification (independent of the reviewer's code).

Exact penalised least squares for statsmodels' GLMGam (Gaussian, identity): minimise
    ||y - [1, B_1, B_2] beta||^2 + 2 * sum_j alpha_j * c_j' C_j c_j        (C_j = smoother.cov_der2)
Independent method (not the reviewer's eigen-threshold): for each smooth the penalty's null space is the linear
function of x_j, whose coefficients c0_j are found by least squares of (x_j - min x_j) on the smooth's basis (exact,
residual printed); the complement P_j comes from an SVD completion of c0_j; the range-space penalty
L_j L_j' = P_j' C_j P_j is factorised by Cholesky and the coordinates gamma_j are rescaled,
gamma_j = (2 alpha_j)^(-1/2) L_j'^(-1) delta_j, so the problem becomes a well-conditioned ridge
    min ||y - Z0 t - Z1 delta||^2 + ||delta||^2
solved by numpy lstsq. The null-space penalty is exactly zero by construction; no threshold anywhere.
edf = trace of the hat matrix from the QR of the augmented matrix; AIC = n + n log(2 pi SSR/n) + 2 edf
(statsmodels' GLM Gaussian llf with the ML scale, k_params = edf).
"""
import sys
import warnings

sys.path.insert(0, "/home/user/MSHI")
import numpy as np
import pandas as pd
from scipy import optimize

from mshi.analysis import transfer as T

ROOT = "/home/user/MSHI"


def standin_sites() -> pd.DataFrame:
    """Analysis QC sites (real coordinates, continent_geo, log_rs) with SRDB-reported MAT/MAP site means as stand-ins
    for bio01/bio12 (WorldClim is unreachable). Sites without MAT or positive MAP are dropped."""
    r = pd.read_parquet(f"{ROOT}/data/derived/records_analysis.parquet")
    srdb = pd.read_csv(f"{ROOT}/data/raw/srdb/srdb-data.csv", usecols=["MAT", "MAP"], low_memory=False)
    r = r[r.site_id_qc.notna() & r.srdb_row.notna()].copy()
    i = r.srdb_row.astype(int).to_numpy()
    r["MAT"], r["MAP"] = srdb.MAT.to_numpy()[i], srdb.MAP.to_numpy()[i]
    r.loc[~(r.MAP > 0), "MAP"] = np.nan
    site = r.groupby("site_id_qc")[["MAT", "MAP"]].mean()
    s = pd.read_parquet(f"{ROOT}/data/derived/sites_analysis_qc.parquet")
    s = s.merge(site, left_on="site_id", right_index=True, how="left").rename(columns={"MAT": "bio01", "MAP": "bio12"})
    s = s[s.bio01.notna() & s.bio12.notna()].sort_values("site_id", kind="mergesort").reset_index(drop=True)
    return s[["site_id", "lon", "lat", "continent_geo", "log_rs", "bio01", "bio12"]]


def basis(spec, train):
    from statsmodels.gam.api import BSplines
    g = spec.gam
    X = T.design(train, g["features"], g["log"])
    y = train[spec.target].to_numpy(float)
    bs = BSplines(X, df=[g["df"]] * X.shape[1], degree=[g["degree"]] * X.shape[1])
    return X, y, bs


class Exact:
    """Exact penalised LS fit at ``alpha`` on (X, y, bs)."""

    def __init__(self, X, y, bs, alpha):
        n = len(y)
        self.bs, self.alpha = bs, np.asarray(alpha, float)
        z0, z1, maps = [np.ones((n, 1))], [], []
        self.null_resid = []
        for a, sm, xj in zip(self.alpha, bs.smoothers, X.T):
            B, C = sm.basis, sm.cov_der2
            c0, *_ = np.linalg.lstsq(B, xj - xj.min(), rcond=None)
            self.null_resid.append(float(np.max(np.abs(B @ c0 - (xj - xj.min())))))
            nv = c0 / np.linalg.norm(c0)
            U = np.linalg.svd(nv[:, None])[0]
            P = U[:, 1:]                                   # orthonormal complement of the null vector
            L = np.linalg.cholesky(P.T @ C @ P)            # range-space penalty, positive definite
            Minv = np.linalg.solve(L.T, np.eye(L.shape[0])) / np.sqrt(2.0 * a)   # gamma = Minv @ delta
            z0.append((B @ nv)[:, None])
            z1.append(B @ P @ Minv)
            maps.append((nv, P @ Minv))
        Z0, Z1 = np.hstack(z0), np.hstack(z1)
        k0, k1 = Z0.shape[1], Z1.shape[1]
        A = np.vstack([np.hstack([Z0, Z1]), np.hstack([np.zeros((k1, k0)), np.eye(k1)])])
        rhs = np.r_[y, np.zeros(k1)]
        sol = np.linalg.lstsq(A, rhs, rcond=None)[0]
        t, delta = sol[:k0], sol[k0:]
        beta, o = [t[0]], 0
        for j, (nv, PM) in enumerate(maps):
            kj = PM.shape[1]
            beta.append(nv * t[1 + j] + PM @ delta[o:o + kj])
            o += kj
        self.params = np.r_[beta[0], np.concatenate(beta[1:])]
        self.fitted = np.hstack([np.ones((n, 1)), bs.basis]) @ self.params
        Q = np.linalg.qr(A)[0]
        self.edf = float(np.sum(Q[:n] ** 2))
        ssr = float(np.sum((y - self.fitted) ** 2))
        self.aic = n + n * np.log(2 * np.pi * ssr / n) + 2 * self.edf

    def predict_x(self, Xn):
        B = np.hstack([T.spline_basis(s, Xn[:, j]) for j, s in enumerate(self.bs.smoothers)])
        return self.params[0] + B @ self.params[1:]


def exact_aic_search(X, y, bs, start=None):
    """The documented search (Nelder-Mead on log alpha from 0, statsmodels' fmin settings) on the exact AIC."""
    k = len(bs.smoothers)
    f = lambda p: Exact(X, y, bs, np.exp(p)).aic
    r = optimize.fmin(f, np.zeros(k) if start is None else start, full_output=True, maxiter=1000, maxfun=2000,
                      disp=False)
    return np.exp(r[0])


def clipped_search(y, bs, log_alpha_max):
    """statsmodels' own PIRLS and AIC, NM from 0 as select_penweight(method='nm'), but alpha = exp(min(p, cap))."""
    from statsmodels.gam.api import GLMGam
    sel = GLMGam(y, exog=np.ones((len(y), 1)), smoother=bs)
    sel.fit()
    hist = {"params": [None]}

    def fun(p):
        a = np.exp(np.minimum(p, log_alpha_max))
        res = sel._fit_pirls(start_params=hist["params"][-1], alpha=a)
        hist["params"].append(np.asarray(res.params))
        return res.aic
    r = optimize.fmin(fun, np.zeros(len(bs.smoothers)), full_output=True, maxiter=1000, maxfun=2000, disp=False)
    alpha = np.exp(np.minimum(r[0], log_alpha_max))
    res = GLMGam(y, exog=np.ones((len(y), 1)), smoother=bs, alpha=alpha).fit()
    return alpha, res


def quiet():
    warnings.simplefilter("ignore")
