import sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
import numpy as np
from mshi.analysis import noise_ceiling as NC
from test_noise_ceiling import simulate

def sums(y, site, study):
    starts = np.flatnonzero(np.r_[True, (site[1:] != site[:-1]) | (study[1:] != study[:-1])])
    m = np.diff(np.r_[starts, len(y)]).astype(float)
    S, Q = np.add.reduceat(y, starts), np.add.reduceat(y * y, starts)
    _, st_site = np.unique(site[starts], return_inverse=True)
    return st_site, m, S, Q, int(st_site.max()) + 1, len(y)

def reml_llf(s2, z):
    sa, sb, se = s2
    st_site, m, S, Q, ns, N = z
    a = 1.0 / (se + m * sb)
    c = np.bincount(st_site, m * a, ns); u = np.bincount(st_site, a * S, ns)
    w = np.bincount(st_site, (Q - sb * a * S * S) / se, ns)
    den = 1.0 + sa * c
    logdet = np.sum((m - 1) * np.log(se) + np.log(se + m * sb)) + np.sum(np.log(den))
    A = np.sum(c / den); b1 = np.sum(u / den); yy = np.sum(w - sa * u * u / den)
    mu = b1 / A
    return -0.5 * ((N - 1) * np.log(2 * np.pi) + logdet + np.log(A) + yy - 2 * mu * b1 + mu * mu * A)

for seed, s2 in [(5, (0.25, 0.0, 0.12)), (1, (0.3, 0.1, 0.05)), (2, (0.0, 0.2, 0.1)), (3, (0.4, 0.05, 0.2))]:
    y, site, study = simulate(seed, 40, s2)
    z = sums(y, site, study)
    for kind in NC.CANDIDATES:
        f = NC._fit_candidate(kind, y, site, study, ("lbfgs", "bfgs", "nm"))
        if f["usable"]:
            mine = reml_llf((f["s2_site"], f["s2_study"], f["s2_record"]), z)
            print(seed, kind, f"sm {f['llf']:.10f} mine {mine:.10f} diff {f['llf'] - mine:.3e}")
