"""Shared helpers for the area-C review scripts (scratch only; reads the repo, writes nothing there)."""
import sys
import numpy as np
import pandas as pd

REPO = "/home/user/MSHI"
SCRATCH = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
if REPO + "/tests" not in sys.path:
    sys.path.insert(0, REPO + "/tests")

CONTINENTS = ["Asia", "Europe", "North America", "South America", "Africa", "Oceania"]


def load_real(variant="qc"):
    """Independent re-derivation of the record table used by the stage (not via mshi.analysis.noise_ceiling)."""
    r = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
    s = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_{variant}.parquet")
    col = f"site_id_{variant}"
    r = r[r[col].notna()].copy()
    r["site"] = r[col].astype(str)
    r = r[r.site.isin(s.site_id)]
    sn = r.Study_number.map(lambda v: str(int(v)) if float(v).is_integer() else repr(float(v)))
    r["study"] = np.where(r.src.eq("srdb"), r.site + "_" + sn.astype(str), "cosore_" + r.rec_id.astype(str))
    r["cont"] = r.site.map(s.set_index("site_id").continent_geo)
    return r, s


def reml_loglik(theta, y, site, study):
    """Full REML log-likelihood of y = mu + a_site + b_study + e at theta = (s2_site, s2_study, s2_rec), intercept
    only. site and study are integer codes; study nested in site. Dense per-site matrices."""
    s2a, s2b, s2e = theta
    if s2e <= 0:
        return -np.inf
    N = len(y)
    ld, xvx, xvy, yvy = 0.0, 0.0, 0.0, 0.0
    for i in np.unique(site):
        m = site == i
        yi = y[m]
        st = study[m]
        n = len(yi)
        V = s2e * np.eye(n) + s2a * np.ones((n, n)) + s2b * (st[:, None] == st[None, :])
        c = np.linalg.cholesky(V)
        ld += 2 * np.log(np.diag(c)).sum()
        one = np.ones(n)
        vinv1 = np.linalg.solve(V, one)
        vinvy = np.linalg.solve(V, yi)
        xvx += one @ vinv1
        xvy += one @ vinvy
        yvy += yi @ vinvy
    beta = xvy / xvx
    q = yvy - 2 * beta * xvy + beta ** 2 * xvx
    p = 1
    return -0.5 * ((N - p) * np.log(2 * np.pi) + ld + np.log(xvx) + q), beta


def codes(df):
    """Integer site and study codes in site, study order (df must be sorted by site then study)."""
    site = pd.factorize(df.site)[0]
    study = pd.factorize(df.site + "|" + df.study)[0]
    return df.log_rs.to_numpy(float), site, study
