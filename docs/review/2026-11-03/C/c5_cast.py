"""Check 5a: an independent numpy transcription of CAST 1.2.0 trainDI() / aoa.data.frame() / .di_threshold()
(R/trainDI.R, R/aoa.R, R/aoa-helpers.R; read, never executed) compared with mshi.analysis.aoa on synthetic data:
- scale(): training means and SAMPLE SDs (R), weights multiplied in, negative weights set to 0;
- trainDist_avrg: per training point, the mean distance to all other training points (self masked);
  trainDist_avrgmean = mean of those;
- trainDist_min: per training point, the min distance to the training points of the CV training set of the fold in
  which the point is held out (CVtrain[[whichfold]]);
- threshold = min(Q3 + 1.5 IQR, max) with R quantile type 7;
- new data DI = min distance to all training points / trainDist_avrgmean; AOA = DI <= threshold.
"""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import numpy as np
from common import REPO  # noqa: F401  (puts the repo on sys.path)
from mshi.analysis import aoa as AOA
from mshi.spatial import block_folds


def r_quantile7(x, p):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    h = (n - 1) * p
    lo = int(np.floor(h))
    hi = min(lo + 1, n - 1)
    return x[lo] + (h - lo) * (x[hi] - x[lo])


def cast_traindi(train, weight, cvtrain, cvtest):
    mu = train.mean(0)
    sd = train.std(0, ddof=1)                      # R's scale(): sample SD
    z = (train - mu) / sd
    w = np.where(weight < 0, 0, weight)
    z = z * w
    n = len(z)
    D = np.sqrt(((z[:, None, :] - z[None, :, :]) ** 2).sum(-1))
    Dm = D.copy()
    np.fill_diagonal(Dm, np.nan)
    avrg = np.nanmean(Dm, axis=1)
    avrgmean = np.mean(avrg)
    mind = np.empty(n)
    for j in range(n):
        f = [k for k, te in enumerate(cvtest) if j in te]
        assert len(f) == 1
        tr = cvtrain[f[0]]
        row = Dm[j].copy()
        mask = np.ones(n, bool)
        mask[tr] = False
        row[mask] = np.nan
        mind[j] = np.nanmin(row)
    tdi = mind / avrgmean
    thr = r_quantile7(tdi, 0.75) + 1.5 * (r_quantile7(tdi, 0.75) - r_quantile7(tdi, 0.25))
    thr = min(thr, tdi.max())
    return dict(mu=mu, sd=sd, w=w, z=z, avrgmean=avrgmean, tdi=tdi, thr=thr)


def cast_di(newdata, t):
    zn = (newdata - t["mu"]) / t["sd"] * t["w"]
    d = np.sqrt(((zn[:, None, :] - t["z"][None, :, :]) ** 2).sum(-1)).min(1)
    return d / t["avrgmean"]


rng = np.random.default_rng(2026)
worst = {"di": 0.0, "tdi": 0.0, "thr": 0.0, "aoa_mismatch": 0}
for case in range(30):
    n, p = int(rng.integers(20, 120)), int(rng.integers(2, 9))
    lon, lat = rng.uniform(-30, 60, n), rng.uniform(-20, 60, n)
    X = rng.normal(size=(n, p)) * rng.uniform(0.1, 50, p) + rng.uniform(-100, 100, p)
    X[rng.random(n) < 0.15] *= 3.0                  # some outlying training points
    w = rng.uniform(-0.2, 1.0, p)                   # some negative importances (CAST: set to 0)
    if w.clip(0).sum() == 0:
        w[0] = 1.0
    folds = list(block_folds(lon, lat, 42, 5.0, 5))
    cvtrain = [tr for tr, va in folds]
    cvtest = [va for tr, va in folds]
    t = cast_traindi(X, w, cvtrain, cvtest)
    Q = rng.normal(size=(200, p)) * X.std(0) * 2 + X.mean(0)
    # the module: weights clipped at 0 and normalised (as importance_weights does); population SD
    wm = np.clip(w, 0, None)
    wm = wm / wm.sum()
    sp = AOA.di_space(X, wm)
    tdi = AOA.training_di(sp, folds)
    thr = AOA.threshold(tdi, {"rule": "fence_capped", "quantiles": [0.25, 0.75], "iqr_multiplier": 1.5})["value"]
    di_m, di_c = sp.di(Q), cast_di(Q, t)
    worst["di"] = max(worst["di"], float(np.max(np.abs(di_m - di_c) / np.maximum(di_c, 1e-12))))
    worst["tdi"] = max(worst["tdi"], float(np.max(np.abs(tdi - t["tdi"]) / np.maximum(t["tdi"], 1e-12))))
    worst["thr"] = max(worst["thr"], abs(thr - t["thr"]) / t["thr"])
    worst["aoa_mismatch"] += int(((di_m <= thr) != (di_c <= t["thr"])).sum())
    # whisker_max (the configured rule) relative to CAST's: never above it, equal when no DI exceeds the fence
    wm_thr = AOA.threshold(tdi, {"rule": "whisker", "quantiles": [0.25, 0.75], "iqr_multiplier": 1.5})
    assert wm_thr["value"] <= thr + 1e-12
    if wm_thr["n_train_above_fence"] == 0:
        assert abs(wm_thr["value"] - thr) < 1e-12
print("max relative differences, module vs CAST transcription over 30 random cases:", worst)
print("dbar: module mean over unordered pairs == CAST mean of per-point averages (checked through the DI above)")
