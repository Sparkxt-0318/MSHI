"""Continent transfer matrix, leave-one-continent-out (LOCO) and the within-continent benchmark (Phase 2, brief
section 5 items 1 and 2; exploratory). Replaces the handoff's E6 (docs/handoff/scripts/exp_matrix.py) and answers
the critique of it (docs/DECISIONS.md F-H18: no uncertainty, pairwise penalties hidden; F-H21: xgboost version;
F-H24: skill relative to the training mean is not comparable with within-continent skill).

Stages
- ``transfer_matrix``: every learner of ``phase2.transfer.learners`` is (a) trained on all sites of continent A and
  scored on every other continent B (pairwise), and (b) trained on the sites of every other continent of
  ``phase2.continents`` and scored on the held-out one (LOCO). A row with fewer than ``phase2.min_test_sites`` test
  sites goes to the supplementary table, the others to the main table; a training set with fewer sites than that
  is skipped (recorded). Per-site predictions go to data/interim/transfer_predictions_<variant>.parquet.
- ``within_continent``: for each continent with at least ``phase2.within.min_sites`` sites, out-of-fold
  predictions of every learner under (i) spatial-block CV (``within.block_deg`` blocks in ``within.folds`` folds, one
  fold assignment per seed of ``within.seeds``) and (ii) kNNDM CV (Linnenbrink et al. 2024; folds from
  ``mshi.analysis.knndm.knndm_folds``, called with every setting of ``within.knndm`` except those of the prediction
  domain, and ``earth_radius_km = site_build.earth_radius_km``; prediction domain = ``max_pred_points`` draws from
  the continent's cells of the ``within.knndm.grid_deg`` climate grid, with probability proportional to cell area
  (``pred_weight: area``, D-P2-7), seeded with the kNNDM seed; with ``exclude_ice_sheets`` the cells of
  ``phase2.aoa.ice_sheets`` are left out first, as no Rs is predicted there (D-P2-16: in North America the whole
  Greenland subunit, ice-free margin included). Each split's W (``knndm.fold_match``: how far its CV
  distances are from the prediction distances) is reported, for the block splits too. The transfer predictions for
  the same sites (LOCO and every pairwise training continent) are read from ``transfer_matrix``'s table, and the
  transfer penalty r2(within) - r2(transfer) gets a paired block-bootstrap CI. Out-of-fold predictions go to
  data/interim/within_predictions_<variant>.parquet.

Sites: ``features_analysis_<phase2.variant>.parquet``. Continents are geographic (``continent_geo``: overseas
territories by location, D-P2-3), never the locked ``continent`` column. A site is used if the target, its
coordinates and every learner's predictors are present and the log-entered predictors are positive, so every
learner is scored on the same sites (rows are paired); sites are sorted by ``site_id`` first, so results do not
depend on the table's row order.

Learners (``phase2.transfer``)
- OLS-TP: least squares on bio01 and ln bio12 (the locked form).
- GAM: statsmodels ``GLMGam`` (Gaussian, identity link): an intercept plus cubic B-spline smooths of bio01 and
  ln bio12 (``gam.df``, ``gam.degree``; knots at training quantiles). The penalty weights are chosen on the training
  data only, by minimising ``gam.penalty_criterion`` (AIC with effective degrees of freedom) over ln alpha with the
  deterministic Nelder-Mead optimiser (``gam.penalty_optimizer: nm``), as ``GLMGam.select_penweight(method="nm")``
  does (start alpha = 1, 1000 iterations, 2000 evaluations; it can stop in a local optimum), except that every
  weight is capped at ``gam.alpha_max`` inside the criterion: above about 1e12 statsmodels' penalised fit starts to
  penalise the linear trend of a smooth (which no weight should), and its AIC then falls spuriously, pulling the
  search to ever larger weights (D-P2-15). At the cap the smooth is linear to within about 1e-4 log units, so a
  smooth whose best shape is linear loses nothing. statsmodels refuses to evaluate B-splines outside the training range,
  so each smooth continues linearly beyond its boundary knots (``gam.extrapolation: linear``: value and slope at the
  boundary), the null space of the second-derivative penalty.
- RF: scikit-learn random forest on ``phase2.c8``, tuned by spatial-block CV inside the training data only: every
  point of ``rf.grid`` is scored by its mean r2 over the inner folds ``block_folds(inner_seed, inner_block_deg,
  inner_folds)`` of the training sites; the best (ties: first in grid order, keys sorted) is refit on all training
  sites. In within-continent CV this runs inside every outer training fold (nested), never on the test fold. Fit
  with ``rf.n_jobs``, predict with ``rf.predict_n_jobs`` (fixed tree-sum order, bit-reproducible; DEV-P1-15).
- XGB: ``xgboost.XGBRegressor`` with the original fixed parameters (the config block named by
  ``transfer.xgb_from``: the locked ones) and ``random_state = transfer.xgb_seed``, on ``phase2.c8``. Library
  versions are recorded in the results (F-H21).

Metrics (log scale unless stated; on the test sites of a row, or on the pooled out-of-fold predictions)
- r2 = 1 - SSE/SST with SST about the mean of the scored sites: skill relative to the test-set mean.
- skill_vs_train_mean = 1 - MSE/MSE_null, the null predicting the training mean (within-continent CV: the mean of
  the training fold that held the site out). It is on the MSE scale (E6 used 1 - RMSE/RMSE_null), so
  MSE_null = SST/n + null_bias_log^2: in transfer it rewards fixing the between-continent offset (F-H24).
  null_bias_log = mean(null - obs) and bias_log = mean(prediction - obs) are reported with it; compare r2, not
  skill_vs_train_mean, between within-continent CV and transfer.
- rmse_log; rmse_rs in g C m-2 yr-1 after a plain exp() back-transform of prediction and observation (no smearing,
  as ``LockedTest.metrics``): exp(prediction) estimates the median and exp(log_rs) is the site's geometric-mean Rs.
- A zero denominator in r2 or skill gives 1 if the errors are all 0, else 0 (scikit-learn's ``r2_score``).
- CIs: spatial-block bootstrap of the scored sites, with the block labels and random draws of
  ``mshi.spatial.bootstrap_ci`` (``bootstrap.block_deg`` blocks resampled with replacement, ``bootstrap.n``
  replicates, the generator re-seeded with ``bootstrap.seed`` for every row, percentile intervals at
  ``bootstrap.quantiles``); every metric is recomputed on each replicate. Rows scored on the same sites share their
  replicates, so differences between them are bootstrapped pairwise. The CIs are conditional on the fitted models:
  training sites are not resampled (as F-H6 notes for the locked test).

Limits
- Exploratory (brief section 5): Europe and North America are used like every other continent; nothing here feeds
  back into the locked test (ground rules 4 and 5).
- Within-continent CV trains on about (folds - 1)/folds of one continent and must reach held-out blocks, LOCO on
  every other continent, so r2(within) is not an upper reference for transfer (F-H18 (b)); training sizes are
  reported with each scheme.
- kNNDM is implemented in ``mshi.analysis.knndm`` (documented and tested there); this module checks that its folds
  partition the sites and records the diagnostics it returns. If it refuses a continent (RuntimeError or
  ValueError), the error is recorded and that continent has no kNNDM result.
"""
from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from ..config import Config
from ..io import read_table, require_outputs, write_result, write_table
from ..spatial import block_folds, block_labels
from .grid import climate_grid

log = logging.getLogger("mshi.transfer")

LEARNERS = ("OLS-TP", "GAM", "RF", "XGB")
METRICS = ("r2", "skill_vs_train_mean", "bias_log", "null_bias_log", "rmse_log", "rmse_rs")
LOCO = "LOCO"
TABLES = ("pairwise", "loco")
NEUTRAL = "#F0EFEC"          # display only: neutral midpoint of the diverging r2 colour scale
R2_FLOOR = -1.0              # display only: lower end of the r2 colour scale and axes (lower values are labelled)
DOMAIN_KEYS = ("grid_deg", "max_pred_points", "pred_weight", "exclude_ice_sheets")   # within.knndm: domain, not kNNDM's



class Untunable(RuntimeError):
    """RF tuning is impossible: the training sites lie in fewer than two inner spatial blocks."""


# ---------------------------------------------------------------- configuration and data

def method_transfer(cfg: Config) -> str:
    p2 = cfg["phase2"]
    tr, B = p2["transfer"], p2["bootstrap"]
    return (f"Pairwise: train on all sites of continent A, score continent B; LOCO: train on every other continent of "
            f"the list, score the held-out one. Learners OLS-TP (bio01, ln bio12), GAM (B-spline smooths of the same, "
            f"penalty by {tr['gam']['penalty_criterion'].upper()} on the training data, linear beyond the boundary "
            f"knots), RF on c8 tuned by spatial-block CV inside the training data, XGB on c8 with the fixed parameters "
            f"of {tr['xgb_from']}. Metrics on log Rs of the test sites: r2 (relative to the test-set mean), "
            f"skill_vs_train_mean (1 - MSE/MSE of the training mean; rewards fixing the between-continent offset, so "
            f"read it with bias_log and null_bias_log), rmse_log, rmse_rs (g C m-2 yr-1, plain exp() back-transform). "
            f"CIs: {B['block_deg']:g}-degree block bootstrap of the test sites ({B['n']} replicates), conditional on "
            f"the fitted model.")


def method_within(cfg: Config) -> str:
    W, B = cfg["phase2"]["within"], cfg["phase2"]["bootstrap"]
    return (f"Per continent with at least {W['min_sites']} sites: pooled out-of-fold predictions of every learner under "
            f"{W['block_deg']:g}-degree spatial-block CV ({W['folds']} folds, one assignment per seed; metrics of the "
            f"seed mean and of each seed) and under kNNDM CV (prediction domain: the continent's "
            f"{W['knndm']['grid_deg']:g}-degree climate-grid cells); RF tuned inside every training fold. The null of "
            f"skill_vs_train_mean is the training-fold mean. Transfer predictions for the same sites (LOCO, pairwise) "
            f"come from transfer_matrix; the penalty r2(within) - r2(transfer) has a paired {B['block_deg']:g}-degree "
            f"block-bootstrap CI (the same resampled blocks for both).")


def _lookup(cfg: Config, dotted: str):
    """The config value at a dotted path such as ``clean_test.locked.xgb``."""
    head, *rest = dotted.split(".")
    node = cfg[head]
    for k in rest:
        node = node[k]
    return node


def xgb_block(cfg: Config) -> tuple[dict, str]:
    """The XGB parameters named by ``phase2.transfer.xgb_from``, and that name. Every Phase-2 stage that fits XGB
    (transfer_matrix, within_continent, aoa_sensitivity, us_r2) takes them from here, so a row that two tables
    share cannot differ between them (review D-1)."""
    name = cfg["phase2"]["transfer"]["xgb_from"]
    xgb = _lookup(cfg, name)
    if not isinstance(xgb, dict):
        raise ValueError(f"phase2.transfer.xgb_from ({name}) does not name a parameter block")
    return dict(xgb), name


@dataclass(frozen=True)
class Spec:
    """Everything that defines the learners and the target (from ``phase2``)."""
    target: str
    c8: list
    ols_tp: dict
    gam: dict
    rf: dict
    xgb: dict
    xgb_seed: int
    xgb_from: str

    @classmethod
    def from_cfg(cls, cfg: Config) -> Spec:
        p2, tr = cfg["phase2"], cfg["phase2"]["transfer"]
        unknown = [x for x in tr["learners"] if x not in LEARNERS]
        if unknown:
            raise ValueError(f"phase2.transfer.learners: unknown {unknown}; implemented: {list(LEARNERS)}")
        if tr["gam"]["extrapolation"] != "linear":
            raise ValueError("phase2.transfer.gam.extrapolation: only 'linear' is implemented")
        if tr["gam"]["penalty_optimizer"] != "nm":
            raise ValueError("phase2.transfer.gam.penalty_optimizer: only 'nm' (deterministic Nelder-Mead) is implemented")
        if not float(tr["gam"]["alpha_max"]) > 0:
            raise ValueError("phase2.transfer.gam.alpha_max must be positive")
        xgb, name = xgb_block(cfg)
        return cls(p2["target"], list(p2["c8"]), dict(tr["ols_tp"]), dict(tr["gam"]), dict(tr["rf"]), xgb,
                   int(tr["xgb_seed"]), name)

    def features(self) -> list[str]:
        """Every predictor any learner uses, in a fixed order."""
        return list(dict.fromkeys(self.c8 + self.ols_tp["features"] + self.gam["features"]))

    def logged(self) -> list[str]:
        return sorted(set(self.ols_tp["log"]) | set(self.gam["log"]))

    def describe(self) -> dict:
        return {"target": self.target, "c8": self.c8, "OLS-TP": self.ols_tp, "GAM": self.gam, "RF": self.rf,
                "XGB": {**self.xgb, "random_state": self.xgb_seed, "from": self.xgb_from}}


def prepare_sites(spec: Spec, raw: pd.DataFrame, continents: list[str]) -> tuple[pd.DataFrame, dict]:
    """The sites every learner is scored on (module docstring), sorted by site_id, and the counts dropped."""
    feats, T = spec.features(), spec.target
    d = raw[["site_id", "lon", "lat", "continent_geo", T] + feats].copy()
    if d.site_id.duplicated().any():
        raise ValueError("features table: site_id is not unique")
    listed = d.continent_geo.isin(continents)
    complete = d[[T, "lon", "lat"] + feats].notna().all(axis=1)
    positive = (d[spec.logged()] > 0).all(axis=1)
    keep = listed & complete & positive
    other = d.loc[~listed, "continent_geo"].astype(object).where(d.continent_geo.notna(), "missing")
    info = {"n_table": int(len(d)), "n_used": int(keep.sum()),
            "n_continent_not_listed": int((~listed).sum()),
            "continent_not_listed": {str(k): int(v) for k, v in sorted(other.value_counts().items())},
            "n_missing_values": int((listed & ~complete).sum()),
            "n_nonpositive_log_predictor": int((listed & complete & ~positive).sum())}
    d = d[keep].sort_values("site_id", kind="mergesort").reset_index(drop=True)
    info["by_continent"] = {c: int((d.continent_geo == c).sum()) for c in continents}
    return d, info


def analysis_sites(cfg: Config, spec: Spec) -> tuple[pd.DataFrame, dict]:
    """Read the analysis features table (a recorded output of a current features_analysis result)."""
    p2 = cfg["phase2"]
    fp = cfg.path("interim", f"features_analysis_{p2['variant']}.parquet")
    require_outputs(cfg, "features_analysis.json", [fp])
    return prepare_sites(spec, read_table(cfg, fp), p2["continents"])


# ---------------------------------------------------------------- learners

@dataclass
class Fitted:
    predict: Callable[[pd.DataFrame], np.ndarray]
    info: dict = field(default_factory=dict)


def design(df: pd.DataFrame, features: list[str], logged: list[str]) -> np.ndarray:
    return np.column_stack([np.log(df[c].to_numpy(float)) if c in logged else df[c].to_numpy(float)
                            for c in features])


def _names(features: list[str], logged: list[str]) -> list[str]:
    return [f"ln {c}" if c in logged else c for c in features]


def spline_basis(smoother, x: np.ndarray) -> np.ndarray:
    """B-spline basis of a fitted statsmodels univariate smoother at ``x``, continued linearly beyond the boundary
    knots (value and first derivative at the boundary)."""
    x = np.asarray(x, float)
    xc = np.clip(x, float(np.min(smoother.knots)), float(np.max(smoother.knots)))
    return smoother.transform(xc) + (x - xc)[:, None] * smoother.transform(xc, deriv=1)


def select_alpha(y: np.ndarray, bs, g: dict) -> tuple[np.ndarray, dict]:
    """Penalty weights minimising ``g["penalty_criterion"]``: Nelder-Mead over ln alpha from 0 with the settings of
    ``GLMGam.select_penweight(method="nm")``, every weight capped at ``g["alpha_max"]`` inside the criterion (module
    docstring). Each evaluation is a fresh fit (statsmodels warm-starts its own; the criterion agrees to 1e-13)."""
    from scipy import optimize
    from statsmodels.gam.api import GLMGam
    ones, cap = np.ones((len(y), 1)), float(np.log(float(g["alpha_max"])))

    def crit(p: np.ndarray) -> float:
        return float(getattr(GLMGam(y, exog=ones, smoother=bs, alpha=np.exp(np.minimum(p, cap))).fit(),
                             g["penalty_criterion"]))
    p, _f, n_iter, n_eval, flag = optimize.fmin(crit, np.zeros(len(bs.smoothers)), full_output=True,
                                                 maxiter=1000, maxfun=2000, disp=False)
    return np.exp(np.minimum(p, cap)), {"at_alpha_max": [bool(v >= cap) for v in p], "n_evaluations": int(n_eval),
                                        "converged": flag == 0}


def fit_gam(spec: Spec, train: pd.DataFrame) -> Fitted:
    from statsmodels.gam.api import BSplines, GLMGam
    g = spec.gam
    X = design(train, g["features"], g["log"])
    y = train[spec.target].to_numpy(float)
    k = X.shape[1]
    bs = BSplines(X, df=[g["df"]] * k, degree=[g["degree"]] * k)
    ones = np.ones((len(X), 1))
    alpha, search = select_alpha(y, bs, g)
    res = GLMGam(y, exog=ones, smoother=bs, alpha=alpha).fit()
    params = np.asarray(res.params, float)

    def predict(df: pd.DataFrame) -> np.ndarray:
        Xn = design(df, g["features"], g["log"])
        B = np.hstack([spline_basis(s, Xn[:, j]) for j, s in enumerate(bs.smoothers)])
        return params[0] + B @ params[1:]
    return Fitted(predict, {"alpha": [float(a) for a in alpha], "edf": float(np.sum(res.edf)),
                            g["penalty_criterion"]: float(getattr(res, g["penalty_criterion"])), **search})


def _rf(spec: Spec, X: np.ndarray, y: np.ndarray, params: dict) -> RandomForestRegressor:
    rf = spec.rf
    m = RandomForestRegressor(n_estimators=rf["n_estimators"], random_state=rf["seed"], n_jobs=rf["n_jobs"],
                              **params).fit(X, y)
    m.set_params(n_jobs=rf["predict_n_jobs"])          # fixed tree-sum order at prediction time
    return m


def rf_grid(rf: dict) -> list[dict]:
    keys = sorted(rf["grid"])
    return [dict(zip(keys, v)) for v in itertools.product(*(rf["grid"][k] for k in keys))]


def tune_rf(spec: Spec, X: np.ndarray, y: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> dict:
    """The grid point with the best mean inner-fold r2 (spatial blocks of the training sites only)."""
    rf = spec.rf
    folds = [(tr, va) for tr, va in block_folds(lon, lat, rf["inner_seed"], rf["inner_block_deg"], rf["inner_folds"])
             if len(tr)]
    if len(folds) < 2:
        raise Untunable(f"{len(y)} training sites in fewer than 2 blocks of {rf['inner_block_deg']} degrees")
    grid = rf_grid(rf)
    scores = [float(np.mean([r2(y[va], _rf(spec, X[tr], y[tr], g).predict(X[va])) for tr, va in folds]))
              for g in grid]
    best = int(np.argmax(scores))
    return {**grid[best], "inner_cv_r2": scores[best], "n_inner_folds": len(folds)}


def fit_learner(spec: Spec, learner: str, train: pd.DataFrame) -> Fitted:
    """Fit ``learner`` on ``train`` only (RF tuning included); the returned ``predict`` takes any site table."""
    y = train[spec.target].to_numpy(float)
    if learner == "OLS-TP":
        o = spec.ols_tp
        lr = LinearRegression().fit(design(train, o["features"], o["log"]), y)
        return Fitted(lambda df: lr.predict(design(df, o["features"], o["log"])),
                      {"intercept": float(lr.intercept_),
                       "coef": dict(zip(_names(o["features"], o["log"]), map(float, lr.coef_)))})
    if learner == "GAM":
        return fit_gam(spec, train)
    X = train[spec.c8].to_numpy("float32")
    if learner == "RF":
        t = tune_rf(spec, X, y, train.lon.to_numpy(float), train.lat.to_numpy(float))
        m = _rf(spec, X, y, {k: t[k] for k in spec.rf["grid"]})
        return Fitted(lambda df: m.predict(df[spec.c8].to_numpy("float32")), t)
    if learner == "XGB":
        import xgboost
        m = xgboost.XGBRegressor(**spec.xgb, random_state=spec.xgb_seed).fit(X, y)
        return Fitted(lambda df: m.predict(df[spec.c8].to_numpy("float32")).astype(float))
    raise ValueError(f"unknown learner {learner!r}")


# ---------------------------------------------------------------- metrics and the block bootstrap

def _skill(err: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """1 - err/ref; a zero ``ref`` gives 1 if ``err`` is 0, else 0 (scikit-learn's ``r2_score``)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        v = 1.0 - err / ref
    return np.where(ref > 0, v, np.where(err == 0, 1.0, 0.0))


def r2(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(_skill(np.array([np.sum((p - y) ** 2)]), np.array([np.sum((y - y.mean()) ** 2)]))[0])


def metric_arrays(y, p, base, idx: np.ndarray, rep: np.ndarray, n_rep: int) -> dict[str, np.ndarray]:
    """Every metric (module docstring) for each replicate: replicate ``rep[i]`` contains site ``idx[i]``."""
    y, p, base = (np.asarray(a, float)[idx] for a in (y, p, base))

    def s(w):
        return np.bincount(rep, weights=w, minlength=n_rep)
    n = np.bincount(rep, minlength=n_rep).astype(float)
    sst = s((y - (s(y) / n)[rep]) ** 2)
    e, e0 = p - y, base - y
    sse, sse0 = s(e ** 2), s(e0 ** 2)
    return {"r2": _skill(sse, sst), "skill_vs_train_mean": _skill(sse, sse0), "bias_log": s(e) / n,
            "null_bias_log": s(e0) / n, "rmse_log": np.sqrt(sse / n),
            "rmse_rs": np.sqrt(s((np.exp(p) - np.exp(y)) ** 2) / n)}


def point_metrics(y, p, base) -> dict:
    n = len(y)
    a = metric_arrays(y, p, base, np.arange(n), np.zeros(n, dtype=int), 1)
    return {"n": int(n), **{k: float(v[0]) for k, v in a.items()}}


@dataclass(frozen=True)
class Replicates:
    """Block-bootstrap replicates of one site set: replicate ``rep[i]`` contains site ``idx[i]``."""
    idx: np.ndarray
    rep: np.ndarray
    n: int


def block_replicates(lon, lat, deg: float, n: int, seed: int) -> Replicates:
    """The draws of ``mshi.spatial.bootstrap_ci(..., deg=deg, n=n, seed=seed)``: the same block labels and the same
    generator calls (``rng.choice(len(u), len(u))`` draws what ``rng.choice(u, len(u))`` draws)."""
    b = block_labels(lon, lat, deg)
    u = np.unique(b)
    members = [np.flatnonzero(b == k) for k in u]
    rng = np.random.default_rng(seed)
    parts = [np.concatenate([members[j] for j in rng.choice(len(u), len(u))]) for _ in range(n)]
    return Replicates(np.concatenate(parts), np.repeat(np.arange(n), [len(x) for x in parts]), n)


def ci(a: np.ndarray, q) -> list[float]:
    return [float(np.quantile(a, q[0])), float(np.quantile(a, q[1]))]


def evaluate(y, p, base, reps: Replicates, q) -> tuple[dict, dict[str, np.ndarray]]:
    """Point metrics with block-bootstrap CIs, and the replicate values (for paired differences)."""
    boot = metric_arrays(y, p, base, reps.idx, reps.rep, reps.n)
    return {**point_metrics(y, p, base), "ci": {k: ci(boot[k], q) for k in METRICS}}, boot


def seed_mean(evals: list[tuple[dict, dict]], q) -> tuple[dict, dict[str, np.ndarray]]:
    """Mean over seeds of each metric; its CI from the per-replicate means (same replicates for every seed)."""
    boot = {k: np.mean([b[k] for _, b in evals], axis=0) for k in METRICS}
    point = {k: float(np.mean([e[k] for e, _ in evals])) for k in METRICS}
    return {"n": evals[0][0]["n"], **point, "ci": {k: ci(boot[k], q) for k in METRICS}}, boot


def _versions() -> dict:
    import sklearn
    import statsmodels
    import xgboost
    return {"numpy": np.__version__, "pandas": pd.__version__, "scikit-learn": sklearn.__version__,
            "statsmodels": statsmodels.__version__, "xgboost": xgboost.__version__}


# ---------------------------------------------------------------- stage 1: transfer matrix and LOCO

def _settings(conts: list[str]) -> list[tuple[str, str, list[str], list[str]]]:
    """(table, train label, training continents, test continents), pairwise first, then LOCO."""
    return ([("pairwise", a, [a], [c for c in conts if c != a]) for a in conts]
            + [("loco", LOCO, [o for o in conts if o != c], [c]) for c in conts])


def _row_key(conts: list[str], learners: list[str]) -> Callable[[dict], tuple]:
    return lambda r: (TABLES.index(r["table"]), learners.index(r["learner"]),
                      conts.index(r["train"]) if r["table"] == "pairwise" else -1, conts.index(r["test"]))


def _tp_range_share(spec: Spec, train: pd.DataFrame, test: pd.DataFrame) -> float:
    """Share of test sites with a TP predictor (bio01, ln bio12) outside the training range."""
    o = spec.ols_tp
    a, b = design(train, o["features"], o["log"]), design(test, o["features"], o["log"])
    return float(((b < a.min(0)) | (b > a.max(0))).any(axis=1).mean())


def transfer_matrix(cfg: Config) -> dict:
    p2 = cfg["phase2"]
    spec = Spec.from_cfg(cfg)
    d, sites = analysis_sites(cfg, spec)
    conts, learners, nmin, B = p2["continents"], p2["transfer"]["learners"], p2["min_test_sites"], p2["bootstrap"]
    T, q = spec.target, B["quantiles"]
    members = {c: np.flatnonzero(d.continent_geo.eq(c).to_numpy()) for c in conts}
    reps: dict[str, Replicates] = {}
    rows, skipped, preds = [], [], []
    for table, label, train_conts, test_conts in _settings(conts):
        tr = d[d.continent_geo.isin(train_conts)]
        tests = [c for c in test_conts if len(members[c])]
        skipped += [{"table": table, "train": label, "test": c, "reason": "no test sites"}
                    for c in test_conts if c not in tests]
        if len(tr) < nmin:
            skipped.append({"table": table, "train": label, "train_continents": train_conts, "n_train": int(len(tr)),
                            "reason": f"training set has fewer than min_test_sites ({nmin}) sites"})
            continue
        for learner in learners:
            log.info("transfer %-8s train %-14s (n=%d) %s", table, label, len(tr), learner)
            try:
                m = fit_learner(spec, learner, tr)
            except Untunable as e:
                skipped.append({"table": table, "train": label, "learner": learner, "reason": f"RF untunable: {e}"})
                continue
            for c in tests:
                te = d.iloc[members[c]]
                if c not in reps:
                    reps[c] = block_replicates(te.lon.to_numpy(), te.lat.to_numpy(), B["block_deg"], B["n"], B["seed"])
                y, p = te[T].to_numpy(float), np.asarray(m.predict(te), float)
                base = np.full(len(te), tr[T].mean())
                ev, _ = evaluate(y, p, base, reps[c], q)
                n_test = ev.pop("n")
                rows.append({"table": table, "train": label, "train_continents": train_conts, "test": c,
                             "learner": learner, "n_train": int(len(tr)), "n_test": n_test, **ev,
                             "frac_test_outside_train_range_tp": _tp_range_share(spec, tr, te), "fit": m.info})
                preds.append(pd.DataFrame({"table": table, "train": label, "test": c, "learner": learner,
                                           "site_id": te.site_id.to_numpy(), "lon": te.lon.to_numpy(float),
                                           "lat": te.lat.to_numpy(float), "obs_log": y, "pred_log": p,
                                           "null_log": base, "n_train": int(len(tr))}))
    key = _row_key(conts, learners)
    order = sorted(range(len(rows)), key=lambda i: key(rows[i]))
    rows = [rows[i] for i in order]
    table_path = cfg.path("interim", f"transfer_predictions_{p2['variant']}.parquet")
    cols = ["table", "train", "test", "learner", "site_id", "lon", "lat", "obs_log", "pred_log", "null_log", "n_train"]
    write_table(pd.concat([preds[i] for i in order], ignore_index=True) if preds else pd.DataFrame(columns=cols),
                table_path)
    figs = transfer_figure(cfg, rows, conts, learners, nmin)
    res = {"exploratory": True, "method": method_transfer(cfg), "variant": p2["variant"], "target": T,
           "continent_column": "continent_geo", "continents": conts, "learners": learners, "min_test_sites": nmin,
           "tables": {"main": f"rows with at least min_test_sites ({nmin}) test sites",
                      "supplementary": f"rows with fewer than {nmin} test sites (brief section 5 item 1: reported in "
                                       "the supplementary table only)"},
           "sites": sites, "bootstrap": B, "learner_settings": spec.describe(), "versions": _versions(),
           "main": [r for r in rows if r["n_test"] >= nmin],
           "supplementary": [r for r in rows if r["n_test"] < nmin], "skipped": skipped,
           "notes": ["exploratory (brief section 5); North America and Europe are used like every other continent "
                     "(ground rules 4 and 5)",
                     "CIs resample test sites only (conditional on the fitted model)",
                     "skill_vs_train_mean rewards fixing the between-continent offset (null_bias_log); compare r2, "
                     "not skill, with within-continent CV (F-H24)"],
           "predictions_table": cfg.root_key(table_path)}
    write_result(cfg, res, "transfer_matrix.json", outputs=[table_path, *figs], inputs=["features_analysis.json"])
    return {"n_main": len(res["main"]), "n_supplementary": len(res["supplementary"]), "n_skipped": len(skipped)}


# ---------------------------------------------------------------- stage 2: within-continent benchmark

def fold_pairs(out, n: int) -> tuple[list[tuple[np.ndarray, np.ndarray]], dict]:
    """(train, test) index pairs from what ``knndm_folds`` returns, and its diagnostics. Accepted: a (fold label per
    site, info dict) tuple (``mshi.analysis.knndm``); a fold label per site (length n); a sequence of (train, test)
    index pairs; either of the last two under the key "folds" (or "clusters") of a mapping whose other entries are
    diagnostics. Arrays among the diagnostics are dropped. The test parts must partition the sites and each train
    part must be the complement of its test part."""
    diag: dict = {}
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        out, diag = out
    elif isinstance(out, dict):
        key = next((k for k in ("folds", "clusters") if k in out), None)
        if key is None:
            raise ValueError(f"kNNDM: no 'folds' or 'clusters' in the returned mapping (keys {sorted(out)})")
        out, diag = out[key], {k: v for k, v in out.items() if k != key}
    diag = {k: (v.item() if isinstance(v, np.generic) else v) for k, v in sorted(diag.items())
            if not isinstance(v, np.ndarray)}
    if not isinstance(out, (np.ndarray, pd.Series)):
        out = list(out)
    if isinstance(out, (np.ndarray, pd.Series)) or (len(out) == n and all(np.isscalar(v) for v in out)):
        lab = np.asarray(out)
        if lab.shape != (n,):
            raise ValueError(f"kNNDM: {lab.shape} fold labels for {n} sites")
        pairs = [(np.flatnonzero(lab != f), np.flatnonzero(lab == f)) for f in np.unique(lab)]
    else:
        pairs = [(np.sort(np.asarray(tr, dtype=int)), np.sort(np.asarray(te, dtype=int))) for tr, te in out]
        pairs = [(tr, te) for tr, te in pairs if len(te)]
    if not pairs or not np.array_equal(np.sort(np.concatenate([te for _, te in pairs])), np.arange(n)):
        raise ValueError("kNNDM: the test folds do not partition the sites")
    if any(len(tr) + len(te) != n or len(np.intersect1d(tr, te)) for tr, te in pairs):
        raise ValueError("kNNDM: a training fold is not the complement of its test fold")
    return pairs, diag


def prediction_domain(grid: pd.DataFrame, continent: str, K: dict) -> np.ndarray:
    """(lon, lat) of the kNNDM prediction points on a continent, seeded with ``K["seed"]``. ``pred_weight: area``:
    ``max_pred_points`` independent draws from the continent's grid cells with probability proportional to cell area
    (``area_km2``), i.e. with replacement, an equal-area sample of the domain (D-P2-7; a lon/lat grid over-represents
    high latitudes); ``none``: a uniform subsample without replacement (all cells if there are fewer)."""
    sel = grid.continent_geo.eq(continent).to_numpy()
    cells = grid.loc[sel, ["lon", "lat"]].to_numpy(float)
    if not len(cells):
        raise ValueError(f"no {K['grid_deg']}-degree climate-grid cells on {continent}")
    rng = np.random.default_rng(K["seed"])
    if K["pred_weight"] == "area":
        w = grid.loc[sel, "area_km2"].to_numpy(float)
        return cells[np.sort(rng.choice(len(cells), K["max_pred_points"], replace=True, p=w / w.sum()))]
    if K["pred_weight"] == "none":
        if len(cells) <= K["max_pred_points"]:
            return cells
        return cells[np.sort(rng.choice(len(cells), K["max_pred_points"], replace=False))]
    raise ValueError(f"within.knndm.pred_weight: {K['pred_weight']!r} is not implemented ('area', 'none')")


def oof_predict(spec: Spec, learner: str, sub: pd.DataFrame, folds) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    """Out-of-fold predictions, the training-fold mean of each site's fold (the null), fold ids and fit info."""
    y = sub[spec.target].to_numpy(float)
    pred, base, fold = np.full(len(sub), np.nan), np.full(len(sub), np.nan), np.full(len(sub), -1)
    infos = []
    for k, (tr, va) in enumerate(folds):
        m = fit_learner(spec, learner, sub.iloc[tr])
        pred[va] = m.predict(sub.iloc[va])
        base[va], fold[va] = y[tr].mean(), k
        infos.append({"fold": k, "n_train": int(len(tr)), "n_test": int(len(va)), **m.info})
    if np.isnan(pred).any():
        raise ValueError("the folds do not cover every site")
    return pred, base, fold, infos


def _transfer_for(tp: pd.DataFrame, sub: pd.DataFrame, continent: str, learner: str) -> dict[str, pd.DataFrame]:
    """Transfer predictions (from transfer_matrix) for the continent's sites, per training label, in site order."""
    t = tp[(tp.test == continent) & (tp.learner == learner)]
    out = {}
    for label, g in t.groupby("train", sort=False):
        g = g.set_index("site_id")
        if set(g.index) != set(sub.site_id):
            raise ValueError(f"transfer predictions {label} -> {continent} ({learner}) are not for the same sites")
        out[label] = g.loc[sub.site_id.to_numpy()]
    return out


def _penalty(within: tuple[dict, dict], other: tuple[dict, dict], q) -> dict:
    (we, wb), (oe, ob) = within, other
    return {"r2_within": we["r2"], "r2_transfer": oe["r2"], "point": we["r2"] - oe["r2"], "ci": ci(wb["r2"] - ob["r2"], q)}


def fold_labels(pairs, n: int) -> np.ndarray:
    lab = np.full(n, -1)
    for k, (_tr, va) in enumerate(pairs):
        lab[va] = k
    return lab


def _knndm(cfg: Config, lonlat: np.ndarray, dom: np.ndarray, knndm_folds: Callable) -> tuple[list | None, dict]:
    """kNNDM folds with every configured setting (``DOMAIN_KEYS`` excepted); (None, error) if kNNDM refuses."""
    kw = {k: v for k, v in cfg["phase2"]["within"]["knndm"].items() if k not in DOMAIN_KEYS}
    try:
        out = knndm_folds(lonlat, dom, **kw, earth_radius_km=cfg["site_build"]["earth_radius_km"])
    except (RuntimeError, ValueError) as e:
        log.warning("kNNDM refused: %s", e)
        return None, {"error": f"{type(e).__name__}: {e}"}
    return fold_pairs(out, len(lonlat))


def cv_splits(cfg: Config, sub: pd.DataFrame, dom: np.ndarray, knndm_folds: Callable,
              fold_match: Callable) -> tuple[dict, dict, dict]:
    """The continent's CV splits ({(scheme, seed): folds}: one spatial-block split per seed, then kNNDM), each split's
    summary with its W (``fold_match``) and the kNNDM record."""
    W, K = cfg["phase2"]["within"], cfg["phase2"]["within"]["knndm"]
    lon, lat = sub.lon.to_numpy(float), sub.lat.to_numpy(float)
    lonlat = np.c_[lon, lat]
    splits = {("blocks", s): list(block_folds(lon, lat, s, W["block_deg"], W["folds"])) for s in W["seeds"]}
    kf, kdiag = _knndm(cfg, lonlat, dom, knndm_folds)
    if kf is not None:
        splits[("knndm", K["seed"])] = kf
    summary, gij = {}, None
    for (name, seed), f in splits.items():
        m = fold_match(lonlat, dom, fold_labels(f, len(sub)), earth_radius_km=cfg["site_build"]["earth_radius_km"])
        summary[f"{name}_{seed}"] = {"n_folds": len(f), "test_sizes": [int(len(va)) for _, va in f],
                                     "mean_n_train": float(np.mean([len(tr) for tr, _ in f])), "W_km": m["W"],
                                     "Gjstar_median_km": m["Gjstar_median_km"]}
        gij = m["Gij_median_km"]                     # the same for every split (sites and prediction points)
    return splits, summary, {"n_pred_points": int(len(dom)), "Gij_median_km": gij, "diagnostics": kdiag}


def _learner(spec: Spec, cfg: Config, sub: pd.DataFrame, splits: dict, reps: Replicates, transfer: dict,
             learner: str) -> tuple[dict, list[dict], list[pd.DataFrame]]:
    """One learner on one continent: metrics per split, the seed mean, the transfer rows and the penalties."""
    W, T = cfg["phase2"]["within"], spec.target
    K, q = W["knndm"], cfg["phase2"]["bootstrap"]["quantiles"]
    y = sub[T].to_numpy(float)
    ev, fits, skipped, preds = {}, {}, [], []
    for (name, seed), folds in splits.items():
        log.info("within %-14s %-6s seed %s %s", sub.continent_geo.iloc[0], name, seed, learner)
        try:
            p, base, fold, infos = oof_predict(spec, learner, sub, folds)
        except Untunable as e:
            skipped.append({"learner": learner, "scheme": name, "seed": seed, "reason": f"RF untunable: {e}"})
            continue
        ev[name, seed], fits[name, seed] = evaluate(y, p, base, reps, q), infos
        preds.append(pd.DataFrame({"continent": sub.continent_geo.iloc[0], "scheme": name, "seed": seed, "fold": fold,
                                   "learner": learner, "site_id": sub.site_id.to_numpy(),
                                   "lon": sub.lon.to_numpy(float), "lat": sub.lat.to_numpy(float), "obs_log": y,
                                   "pred_log": p, "null_log": base}))
    L: dict = {}
    within = {}
    if all(("blocks", s) in ev for s in W["seeds"]):
        within["blocks"] = seed_mean([ev["blocks", s] for s in W["seeds"]], q)
        L["blocks"] = {"seed_mean": within["blocks"][0],
                       "per_seed": [{"seed": s, **ev["blocks", s][0], "fit": fits["blocks", s]} for s in W["seeds"]]}
    if ("knndm", K["seed"]) in ev:
        within["knndm"] = ev["knndm", K["seed"]]
        L["knndm"] = {**within["knndm"][0], "fit": fits["knndm", K["seed"]]}
    first = ev.get(("blocks", W["seeds"][0]))
    L["transfer"], L["penalty_r2"] = {}, {}
    for label, g in transfer.items():
        other = evaluate(y, g.pred_log.to_numpy(float), g.null_log.to_numpy(float), reps, q)
        L["transfer"][label] = other[0]
        pen = {k: _penalty(w, other, q) for k, w in within.items()}
        if label == LOCO and first is not None:
            pen["blocks_first_seed"] = {"seed": W["seeds"][0], **_penalty(first, other, q)}
        L["penalty_r2"][label] = pen
    return L, skipped, preds


def _continent(spec: Spec, cfg: Config, sub: pd.DataFrame, dom: np.ndarray, tp: pd.DataFrame, n_train: dict,
               knndm_folds: Callable, fold_match: Callable) -> tuple[dict, list[pd.DataFrame]]:
    B = cfg["phase2"]["bootstrap"]
    reps = block_replicates(sub.lon.to_numpy(float), sub.lat.to_numpy(float), B["block_deg"], B["n"], B["seed"])
    splits, summary, kn = cv_splits(cfg, sub, dom, knndm_folds, fold_match)
    entry = {"n": int(len(sub)), "splits": summary, "knndm": kn,
             "transfer_n_train": {k: n_train[k] for k in sorted(n_train, key=lambda x: (x != LOCO, x))},
             "learners": {}, "skipped": []}
    preds = []
    for learner in cfg["phase2"]["transfer"]["learners"]:
        transfer = _transfer_for(tp, sub, sub.continent_geo.iloc[0], learner)
        entry["learners"][learner], skipped, p = _learner(spec, cfg, sub, splits, reps, transfer, learner)
        entry["skipped"] += skipped
        preds += p
    return entry, preds


def within_continent(cfg: Config) -> dict:
    p2 = cfg["phase2"]
    spec = Spec.from_cfg(cfg)
    d, sites = analysis_sites(cfg, spec)
    tp_path = cfg.path("interim", f"transfer_predictions_{p2['variant']}.parquet")
    tm = require_outputs(cfg, "transfer_matrix.json", [tp_path])
    tp = read_table(cfg, tp_path)
    conts, W = p2["continents"], p2["within"]
    counts = sites["by_continent"]
    eligible = [c for c in conts if counts[c] >= W["min_sites"]]
    res = {"exploratory": True, "method": method_within(cfg), "variant": p2["variant"], "target": spec.target,
           "continent_column": "continent_geo", "learners": p2["transfer"]["learners"], "within": W,
           "bootstrap": p2["bootstrap"], "sites": sites, "versions": _versions(),
           "skipped": [{"continent": c, "n": counts[c], "reason": f"fewer than within.min_sites ({W['min_sites']}) sites"}
                       for c in conts if c not in eligible],
           "penalty_definition": ("r2(within-continent CV) - r2(transfer to the continent), on the same sites; "
                                  "blocks = spatial-block CV, mean over seeds (CI from the per-replicate seed mean), "
                                  "blocks_first_seed = first seed only (LOCO), knndm = kNNDM CV; paired CI from the "
                                  "same resampled blocks"),
           "continents": {}, "notes": ["exploratory (brief section 5); North America and Europe are used like every "
                                       "other continent (ground rules 4 and 5)",
                                       "within-continent CV trains on fewer sites than transfer (splits' mean_n_train vs "
                                       "transfer_n_train), so r2(within) is not an upper reference (F-H18 (b))",
                                       "transfer metrics recomputed from transfer_matrix's predictions with the same "
                                       "bootstrap; they equal the rows of results/transfer_matrix.json"]}
    inputs, preds = ["features_analysis.json", "transfer_matrix.json"], []
    if eligible:
        from .knndm import fold_match, knndm_folds      # mshi.analysis.knndm: imported here, at use
        grid = climate_grid(cfg, W["knndm"]["grid_deg"])
        inputs.append("fetch_worldclim.json")
        dom = {"n_cells": int(len(grid)), "exclude_ice_sheets": bool(W["knndm"]["exclude_ice_sheets"])}
        if W["knndm"]["exclude_ice_sheets"]:
            from .aoa import ice_sheet_mask             # imported here: aoa imports this module
            ice, counts = ice_sheet_mask(cfg, grid, p2["aoa"]["ice_sheets"])
            dom.update(ice_sheets=dict(p2["aoa"]["ice_sheets"]), ice_cells=counts,
                       ice_cells_by_continent={str(k): int(v) for k, v in
                                               grid.loc[ice, "continent_geo"].value_counts().sort_index().items()})
            grid = grid[~ice].reset_index(drop=True)
        dom["n_cells_used"] = int(len(grid))
        res["prediction_domain"] = dom
        rows = tm["main"] + tm["supplementary"]
        for c in eligible:
            sub = d[d.continent_geo == c].reset_index(drop=True)
            n_train = {r["train"]: r["n_train"] for r in rows if r["test"] == c}
            res["continents"][c], p = _continent(spec, cfg, sub, prediction_domain(grid, c, W["knndm"]), tp, n_train,
                                                 knndm_folds, fold_match)
            preds += p
    table_path = cfg.path("interim", f"within_predictions_{p2['variant']}.parquet")
    cols = ["continent", "scheme", "seed", "fold", "learner", "site_id", "lon", "lat", "obs_log", "pred_log",
            "null_log"]
    write_table(pd.concat(preds, ignore_index=True) if preds else pd.DataFrame(columns=cols), table_path)
    figs = within_figure(cfg, res["continents"], res["learners"]) if res["continents"] else []
    res["predictions_table"] = cfg.root_key(table_path)
    write_result(cfg, res, "within_continent.json", outputs=[table_path, *figs], inputs=inputs)
    return {"continents": list(res["continents"]), "n_skipped": len(res["skipped"])}


# ---------------------------------------------------------------- figures

def _fmt(v: float) -> str:
    """Two decimals below 1 in magnitude, then fewer, so labels fit their cells."""
    return f"{v:.2f}" if abs(v) < 1 else f"{v:.1f}" if abs(v) < 10 else f"{v:.0f}"


def _xlabel(name: str) -> str:
    return "all others\n(LOCO)" if name == LOCO else name.replace(" ", "\n")


def transfer_figure(cfg: Config, rows: list[dict], conts: list[str], learners: list[str], nmin: int) -> list[Path]:
    """r2 matrix per learner: rows = test continent, columns = training continent and LOCO; hatched cells have fewer
    than ``nmin`` test sites (supplementary table); each cell shows r2 and its 95% block-bootstrap CI. Colours run
    from ``R2_FLOOR`` to 1 (r2 cannot exceed 1); lower values take the end colour, the text gives the value."""
    import matplotlib.pyplot as plt
    from matplotlib import patheffects
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    from matplotlib.patches import Patch, Rectangle

    from ..figures.style import PALETTE, save_figure
    trains = [c for c in conts if any(r["table"] == "pairwise" and r["train"] == c for r in rows)] + [LOCO]
    norm = TwoSlopeNorm(vmin=R2_FLOOR, vcenter=0.0, vmax=1.0)
    cmap = LinearSegmentedColormap.from_list("r2", [PALETTE["vermillion"], NEUTRAL, PALETTE["blue"]]).with_extremes(
        bad="white")
    nc = 2 if len(learners) > 1 else 1
    nr = -(-len(learners) // nc)
    fig, axes = plt.subplots(nr, nc, figsize=(7.2, 2.9 * nr + 0.5), squeeze=False, constrained_layout=True)
    im = None
    for ax, learner in zip(axes.flat, learners):
        M = np.full((len(conts), len(trains)), np.nan)
        cells = {}
        for r in rows:
            if r["learner"] == learner:
                ij = (conts.index(r["test"]), trains.index(LOCO if r["table"] == "loco" else r["train"]))
                M[ij], cells[ij] = r["r2"], r
        im = ax.imshow(np.ma.masked_invalid(M), cmap=cmap, norm=norm, aspect="auto")
        for (i, j), r in sorted(cells.items()):
            face = np.asarray(cmap(norm(r["r2"]))[:3])
            ink = "white" if face @ np.array([0.2126, 0.7152, 0.0722]) < 0.45 else PALETTE["black"]
            supp = r["n_test"] < nmin
            if supp:
                hatch = Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, hatch="///", hatchcolor=PALETTE["grey"],
                                  linewidth=0)
                hatch.set_hatch_linewidth(0.4)
                ax.add_patch(hatch)
            halo = [patheffects.withStroke(linewidth=2.2, foreground=face)] if supp else None
            lo, hi = r["ci"]["r2"]
            ax.text(j, i - 0.14, _fmt(r["r2"]), ha="center", va="center", fontsize=6.5, color=ink, path_effects=halo)
            ax.text(j, i + 0.22, f"{_fmt(lo)}, {_fmt(hi)}", ha="center", va="center", fontsize=5, color=ink,
                    path_effects=halo)
        for i, c in enumerate(conts):
            if c in trains:
                ax.text(trains.index(c), i, "–", ha="center", va="center", fontsize=7, color=PALETTE["grey"])
        ax.axvline(len(trains) - 1.5, color="white", linewidth=2.5)
        ax.set_xticks(range(len(trains)), [_xlabel(t) for t in trains])
        ax.set_yticks(range(len(conts)), conts)
        ax.tick_params(length=0)
        ax.set_title(learner)
        ax.set_xlabel("trained on")
        ax.set_ylabel("tested on")
        for sp in ax.spines.values():
            sp.set_visible(False)
    for ax in axes.flat[len(learners):]:
        ax.set_visible(False)
    if im is not None:
        fig.colorbar(im, ax=axes, shrink=0.55, extend="min", label="R² (log Rs, relative to the test-set mean)")
    key = Patch(facecolor="white", hatch="///", edgecolor=PALETTE["grey"], linewidth=0.4,
                label=f"fewer than {nmin} test sites (supplementary table)")
    fig.legend(handles=[key], loc="outside lower center", frameon=False)
    return save_figure(fig, cfg.path("figures", "phase2", "transfer_matrix"))


def within_figure(cfg: Config, entries: dict, learners: list[str]) -> list[Path]:
    """Per continent and learner: r2 with its 95% CI under spatial-block CV (seed mean), kNNDM CV and LOCO. The axis
    stops at ``R2_FLOOR``: a lower r2 is drawn on the floor with its value; CIs are cut there."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from ..figures.style import PALETTE, save_figure
    W = cfg["phase2"]["within"]
    styles = [("blocks", f"{W['block_deg']:g}° blocks (mean of {len(W['seeds'])} seeds)",
               dict(marker="o", color=PALETTE["black"], mfc=PALETTE["black"])),
              ("knndm", "kNNDM", dict(marker="s", color=PALETTE["grey"], mfc=PALETTE["grey"])),
              (LOCO, "leave-one-continent-out", dict(marker="^", color=PALETTE["black"], mfc="white"))]

    def got(L: dict) -> dict:
        return {"blocks": L.get("blocks", {}).get("seed_mean"), "knndm": L.get("knndm"),
                LOCO: L.get("transfer", {}).get(LOCO)}
    lows = [m["ci"]["r2"][0] for e in entries.values() for L in e["learners"].values() for m in got(L).values() if m]
    conts = list(entries)
    fig, axes = plt.subplots(1, len(conts), figsize=(7.2, 2.6), sharey=True, squeeze=False, constrained_layout=True)
    for ax, c in zip(axes[0], conts):
        for li, learner in enumerate(learners):
            m_by = got(entries[c]["learners"].get(learner, {}))
            for si, (key, _label, st) in enumerate(styles):
                m, x = m_by[key], li + (si - 1) * 0.24
                if not m:
                    continue
                kw = dict(color=st["color"], mfc=st["mfc"], mec=st["color"], ms=4.5)
                if m["r2"] < R2_FLOOR:
                    ax.plot(x, R2_FLOOR, marker=st["marker"], clip_on=False, **kw)
                    ax.annotate(_fmt(m["r2"]), (x, R2_FLOOR), xytext=(0, 5), textcoords="offset points",
                                ha="center", va="bottom", fontsize=5.5, color=PALETTE["black"])
                    continue
                lo, hi = m["ci"]["r2"]
                ax.errorbar(x, m["r2"], yerr=[[m["r2"] - lo], [hi - m["r2"]]], fmt=st["marker"], elinewidth=1,
                            capsize=0, **kw)
        ax.axhline(0.0, color=PALETTE["grey"], linewidth=0.6, zorder=0)
        ax.set_xticks(range(len(learners)), learners)
        ax.set_xlim(-0.6, len(learners) - 0.4)
        ax.set_title(f"{c} (n = {entries[c]['n']})")
    if lows and min(lows) < R2_FLOOR:
        axes[0][0].set_ylim(bottom=R2_FLOOR - 0.05)
    axes[0][0].set_ylabel("R² (log Rs)")
    fig.legend(handles=[Line2D([], [], linestyle="none", marker=st["marker"], color=st["color"], mfc=st["mfc"],
                               mec=st["color"], ms=4.5, label=label) for _k, label, st in styles],
               loc="outside lower center", ncols=3, frameon=False)
    return save_figure(fig, cfg.path("figures", "phase2", "within_continent"))
