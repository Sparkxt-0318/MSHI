"""Area-of-applicability (AOA) sensitivity (Phase 2, brief section 5 item 4; exploratory). Replaces the handoff's E5
(docs/handoff/scripts/exp_global_aoa.py) and answers the critique of it (docs/DECISIONS.md F-H25).

Stage ``aoa_sensitivity``. For every training set of ``phase2.aoa.train`` ("all": the sites of every continent of
``phase2.continents``; a continent name: the sites of that continent), every weighting of ``aoa.weights`` and every
threshold of ``aoa.thresholds``: the dissimilarity index (DI) of each cell of the global ``aoa.grid_deg`` land grid
with respect to an XGBoost model of log Rs on the bioclim predictors ``phase2.c8``, its area of applicability (AOA =
DI <= threshold), and the shares of land area and of predicted Rs flux outside the AOA, overall, by geographic
continent and by latitude band, over all land cells and without the ice sheets. For the model of
``aoa.transfer_check.train`` (Asia): the sites of ``transfer_check.test`` (North America) inside vs outside its AOA.

Inputs
- Sites: data/interim/features_analysis_<phase2.variant>.parquet, a recorded output of a current
  ``features_analysis`` result. Continents are geographic (``continent_geo``: overseas territories by location,
  D-P2-3), never the locked ``continent`` column. A site is used if its continent is listed in ``phase2.continents``
  and its target, coordinates and every c8 value are present. Sites are sorted by ``site_id`` first, so results do
  not depend on the table's row order.
- Grid: ``mshi.analysis.grid.climate_grid`` at ``aoa.grid_deg`` (WorldClim 2.1 bioclim values at cell centres, the
  cell's area on the sphere, ``continent_geo``; it verifies the rasters against the current fetch_worldclim result).

Model and DI (Meyer & Pebesma 2021, doi:10.1111/2041-210X.13650; as ``LockedTest.aoa`` and the handoff's E5)
- XGBoost with the locked fixed parameters (``clean_test.locked.xgb``), random_state ``phase2.transfer.xgb_seed``,
  fitted on the training set's c8 values as float32 (as LockedTest and mshi.analysis.transfer).
- Weighted predictor space: each predictor is standardised with the training mean and SD (population SD; a constant
  predictor gets SD 1) and multiplied by a weight. "permutation": scikit-learn ``permutation_importance`` of the
  fitted model on its training data (score R2, ``aoa.perm_repeats`` repeats, random_state ``aoa.perm_seed``), mean
  importances clipped at 0 and normalised to sum 1; if none is positive, equal weights (recorded as a fallback, as
  LockedTest). "none": equal weights 1/p. The DI is unchanged when every weight is multiplied by the same factor, so
  equal weights give the unweighted standardised distance.
- DI(x) = Euclidean distance from x to the nearest training point / the mean distance over all pairs of training
  points, in the weighted space.
- Training DI: spatial-block CV folds (``mshi.spatial.block_folds`` with ``aoa.cv``: block_deg, folds, seed); a
  training point's DI is its distance to the nearest training point of the other folds, over the same mean.
- Thresholds (``aoa.threshold_rules``; each name in ``aoa.thresholds`` names a rule): ``whisker`` = the largest
  training DI not above Q3 + m IQR (the "outlier-removed maximum" of LockedTest.aoa and E5; quantiles and m from the
  config, numpy's linear quantiles = R type 7); ``quantile`` = that quantile of the training DI (q95); ``fence_capped``
  = min(Q3 + m IQR, largest training DI), the rule of CAST 1.2.0 (see Sources; not configured by default). For a
  whisker rule the fence Q3 + m IQR, the number of training DI above it and the largest training DI are reported, so
  CAST's threshold can be read off.
- AOA: DI <= threshold (CAST: outside if DI > threshold).

Reported (``variants``: training set x threshold x weights, in config order)
- The threshold, the share of training DI above it, and for each domain, "all_land" (every grid cell) and
  "excluding_ice_sheets": the share of land area outside the AOA (cell areas from climate_grid) and the share of
  predicted Rs flux outside the AOA, overall, by ``continent_geo`` (cells without one: "unassigned") and by latitude
  band (``aoa.lat_bands``: cell-centre latitude, intervals (lower, upper]).
- Ice sheets (``aoa.ice_sheets``; F-H25): cells whose ``continent_geo`` is listed (Antarctica), every cell centred
  south of ``south_of_lat`` (-60: only Antarctica and its islands lie there, so ice-shelf cells that Natural Earth's
  subunits leave unassigned are caught too), and cells whose Natural Earth 1:50m map subunit is listed (Greenland),
  found with ``mshi.geo.geographic_continent`` (the rule that gives climate_grid its ``continent_geo``: the subunit
  that contains the cell centre, else the nearest within ``site_build.continent.nearest_max_m``, geodesic). A cell
  matched to a subunit carries that subunit's continent, so it is run only on the cells not yet removed whose
  ``continent_geo`` is a listed subunit's (North America for Greenland); a name that is not a subunit, or a subunit of
  Russia (whose cells mshi.geo assigns by longitude), is refused. The cells each criterion finds are counted in
  ``grid.ice_sheets``.
- Flux: exp(predicted log Rs) x the Duan (1983) smearing factor of the model (mean of exp(training residual)) x cell
  area. A share is a ratio of two sums over cells of one model, so the smearing factor cancels: the share depends only
  on where the model predicts high Rs. No global total is reported (F-H25: E5's 87.3 Pg C/yr was a median-based sum
  over a grid including ice sheets and barren land).
- ``transfer_check``: the model of the named training set predicts the named continent's sites (not in its training
  set); n, r2 (relative to the mean of the scored sites) and rmse_log of all of them and of those inside and outside
  each AOA variant, with spatial-block bootstrap CIs (``phase2.bootstrap``; mshi.spatial.bootstrap_ci; conditional on
  the fitted model). Exploratory (ground rule 5).
- Outputs: data/interim/aoa_di_grid.parquet (gitignored: WorldClim-derived): per cell the coordinates, area,
  continent, latitude band, ice-sheet flag, the predicted log Rs of each training set's model, the DI of each training
  set x weights and the AOA flag of each variant; figures phase2/aoa_di_map (the DI of the primary variant = the
  first entry of each list: all sites, whisker_max, permutation weights; its AOA boundary and training sites) and
  phase2/aoa_variants (the AOA of every variant).

Differences from E5: no global total and the smearing factor (F-H25); ice sheets reported separately (E5's grid kept
Greenland and ended at 60 S); the whole climate grid (E5: 60 S - 84 N, and a bio05 > -50 filter); exact cell areas
(E5: (111.32 x 0.5)^2 cos(lat)); the mean distance over all pairs (E5: the first 400,000 pairs in upper-triangle
order after a random permutation; for its 967 sites 86% of the pairs, leaving out those among the last 367 sites);
geographic continents (E5: the locked country rule, and no continent breakdown); weights 'none' and the q95 threshold as
sensitivity variants; library versions recorded (F-H21).

Sources. The paper could not be read (doi.org, the publisher and arXiv are blocked here). The DI, the CV-based training
DI and the AOA rule were checked against the authors' R package CAST 1.2.0 (GitHub HannaMeyer/CAST, branch master,
read 2026-11-03; R/trainDI.R SHA-256 6eae450e..., R/aoa.R e0d32358..., R/aoa-helpers.R a69bfa97...): predictors
``scale()``d and multiplied by the weights (negative weights set to 0), training DI = distance to the nearest training
point of the point's CV training set / the mean over points of the average distance to all other points (= the mean
over all pairs), AOA = DI <= threshold. CAST weights by "the internal variable importance" of the model (its
documentation; the example uses caret's ``varImp``), not by permutation importance as here. Its threshold
(``.di_threshold``) is min(Q3 + 1.5 IQR, largest training DI): the fence itself when some training DI lie above it, so
at least ``whisker_max``; the two differ only then, by the gap between the fence and the largest training DI below it.
The brief and the handoff use the outlier-removed maximum, kept here.

Limits. Exploratory (brief section 5). The training set "all" includes Europe and North America (as E5); nothing here
feeds back into the locked test (ground rule 4). The DI uses the c8 climate space only (the predictors mapped
globally); soil and MODIS predictors are not used. Permutation importance on the training data measures what the
fitted model uses, not out-of-sample importance. The training DI, so the thresholds, depend on the CV design (5-degree
blocks). The smearing factor uses in-sample residuals of a boosted model (smaller than an out-of-sample factor); it
cancels in every reported share. Barren land (deserts, rock) is not removed: Phase 2 has no land cover. Cell areas are
whole lon/lat cells, including the sea part of coastal cells. The bootstrap CIs resample sites in blocks around one
fitted model; training sites are not resampled (as F-H6 notes for the locked test).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist, pdist
from sklearn.inspection import permutation_importance

from ..config import Config
from ..geo import geographic_continent, subunits
from ..io import read_table, require_outputs, write_result, write_table
from ..spatial import block_folds, bootstrap_ci
from .grid import climate_grid

log = logging.getLogger("mshi.aoa")

TRAIN_ALL = "all"            # config vocabulary (aoa.train): the sites of every continent of phase2.continents
KEYS = ("learner", "train", "thresholds", "threshold_rules", "weights", "grid_deg", "perm_repeats", "perm_seed", "cv",
        "lat_bands", "ice_sheets", "transfer_check")      # phase2.aoa keys this module reads
WEIGHTS = ("permutation", "none")
RULES = ("whisker", "quantile", "fence_capped")
DOMAINS = ("all_land", "excluding_ice_sheets")
UNASSIGNED = "unassigned"    # label of grid cells that have no geographic continent
CHUNK_ROWS = 4096            # query rows per distance block (memory only)
DI_VMAX_FACTOR = 3.0         # display only: the DI colour scale ends at this multiple of the threshold


# ---------------------------------------------------------------- configuration

def aoa_settings(cfg: Config) -> dict:
    """``phase2.aoa``, checked: names that select code paths must be implemented and consistent."""
    p2 = cfg["phase2"]
    A = p2["aoa"]
    missing = [k for k in KEYS if k not in A]
    if missing:
        raise ValueError(f"phase2.aoa lacks {missing} (the settings mshi/analysis/aoa.py reads)")
    if A["learner"] != "XGB":
        raise ValueError(f"phase2.aoa.learner: only 'XGB' is implemented, got {A['learner']!r}")
    bad = [w for w in A["weights"] if w not in WEIGHTS]
    if bad:
        raise ValueError(f"phase2.aoa.weights: unknown {bad}; implemented: {list(WEIGHTS)}")
    rules = A["threshold_rules"]
    missing = [t for t in A["thresholds"] if t not in rules]
    if missing:
        raise ValueError(f"phase2.aoa.thresholds {missing} have no entry in phase2.aoa.threshold_rules")
    bad = [t for t in A["thresholds"] if rules[t]["rule"] not in RULES]
    if bad:
        raise ValueError(f"phase2.aoa.threshold_rules: unknown rule for {bad}; implemented: {list(RULES)}")
    for t in A["train"]:
        if t != TRAIN_ALL and t not in p2["continents"]:
            raise ValueError(f"phase2.aoa.train: {t!r} is neither '{TRAIN_ALL}' nor one of phase2.continents")
    tc = A["transfer_check"]
    if tc["train"] not in A["train"]:
        raise ValueError(f"phase2.aoa.transfer_check.train {tc['train']!r} is not in phase2.aoa.train")
    if tc["test"] in train_continents(tc["train"], p2["continents"]) or tc["test"] not in p2["continents"]:
        raise ValueError(f"phase2.aoa.transfer_check.test {tc['test']!r} must be a listed continent outside the "
                         f"training set {tc['train']!r}")
    b = A["lat_bands"]
    if len(b["labels"]) != len(b["edges"]) - 1 or list(b["edges"]) != sorted(set(b["edges"])):
        raise ValueError("phase2.aoa.lat_bands: edges must increase and there must be one label per interval")
    return A


def train_continents(name: str, continents: list[str]) -> list[str]:
    return list(continents) if name == TRAIN_ALL else [name]


def method_text(cfg: Config) -> str:
    A, p2 = cfg["phase2"]["aoa"], cfg["phase2"]
    return (f"XGB (clean_test.locked.xgb, random_state phase2.transfer.xgb_seed) of {p2['target']} on c8 per training "
            f"set {A['train']}; DI (Meyer & Pebesma 2021, as LockedTest.aoa and CAST 1.2.0): predictors standardised "
            f"with the training mean/SD and weighted (permutation importance clipped at 0 and normalised, or equal), "
            f"distance to the nearest training point / mean pairwise training distance; training DI from "
            f"{A['cv']['block_deg']}-degree spatial-block CV (nearest point of the other folds); thresholds "
            f"{A['thresholds']}; AOA = DI <= threshold; shares of land area and of predicted Rs flux "
            f"(exp(prediction) x Duan smearing x cell area; the smearing factor cancels) outside the AOA on the "
            f"{A['grid_deg']}-degree WorldClim land grid, over all land cells and excluding ice sheets; no global "
            f"total. {A['transfer_check']['test']} sites inside vs outside the AOA of the "
            f"{A['transfer_check']['train']} model (exploratory).")


def _versions() -> dict:
    import scipy
    import sklearn
    import xgboost
    return {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__}


def _slug(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_")


# ---------------------------------------------------------------- sites

def prepare_sites(raw: pd.DataFrame, target: str, c8: list[str], continents: list[str]) -> tuple[pd.DataFrame, dict]:
    """The usable sites (module docstring), sorted by site_id, and the counts left out."""
    d = raw[["site_id", "lon", "lat", "continent_geo", target] + list(c8)].copy()
    if d.site_id.duplicated().any():
        raise ValueError("features table: site_id is not unique")
    listed = d.continent_geo.isin(continents)
    complete = d[[target, "lon", "lat"] + list(c8)].notna().all(axis=1)
    keep = listed & complete
    info = {"n_table": int(len(d)), "n_used": int(keep.sum()), "n_continent_not_listed": int((~listed).sum()),
            "n_missing_values": int((listed & ~complete).sum())}
    d = d[keep].sort_values("site_id", kind="mergesort").reset_index(drop=True)
    info["by_continent_geo"] = {c: int((d.continent_geo == c).sum()) for c in continents}
    return d, info


def analysis_sites(cfg: Config) -> tuple[pd.DataFrame, dict]:
    """Read the analysis features table (a recorded output of a current features_analysis result)."""
    p2 = cfg["phase2"]
    fp = cfg.path("interim", f"features_analysis_{p2['variant']}.parquet")
    require_outputs(cfg, "features_analysis.json", [fp])
    return prepare_sites(read_table(cfg, fp), p2["target"], p2["c8"], p2["continents"])


# ---------------------------------------------------------------- model, weights and DI

def fit_xgb(cfg: Config, X32: np.ndarray, y: np.ndarray):
    import xgboost
    return xgboost.XGBRegressor(**cfg["clean_test"]["locked"]["xgb"],
                                random_state=cfg["phase2"]["transfer"]["xgb_seed"]).fit(X32, y)


def importance_weights(kind: str, model, X: np.ndarray, y: np.ndarray, repeats: int,
                       seed: int) -> tuple[np.ndarray, bool]:
    """(weights summing to 1, True if the permutation importances were all <= 0 and equal weights were used)."""
    p = X.shape[1]
    equal = np.full(p, 1.0 / p)
    if kind == "none":
        return equal, False
    if kind != "permutation":
        raise ValueError(f"unknown weights {kind!r}; implemented: {list(WEIGHTS)}")
    imp = permutation_importance(model, X, y, n_repeats=repeats, random_state=seed).importances_mean
    w = np.clip(imp, 0.0, None)
    return (w / w.sum(), False) if w.sum() > 0 else (equal, True)


def nearest_distance(zq: np.ndarray, zr: np.ndarray, chunk: int = CHUNK_ROWS) -> np.ndarray:
    """Euclidean distance from each row of ``zq`` to the nearest row of ``zr`` (exact; blocks of ``chunk`` rows)."""
    if len(zr) == 0:
        raise ValueError("no reference points")
    out = np.empty(len(zq))
    for s in range(0, len(zq), chunk):
        out[s:s + chunk] = cdist(zq[s:s + chunk], zr).min(axis=1)
    return out


@dataclass(frozen=True)
class DISpace:
    """The weighted, standardised predictor space of one training set and its mean pairwise distance."""
    mu: np.ndarray
    sd: np.ndarray
    w: np.ndarray
    z: np.ndarray            # training points in the weighted space
    dbar: float              # mean distance over all pairs of training points

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (np.asarray(X, float) - self.mu) / self.sd * self.w

    def di(self, X: np.ndarray) -> np.ndarray:
        return nearest_distance(self.transform(X), self.z) / self.dbar


def di_space(X: np.ndarray, w: np.ndarray) -> DISpace:
    X = np.asarray(X, float)
    if len(X) < 2:
        raise ValueError("the DI needs at least two training points")
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd == 0, 1.0, sd)
    w = np.asarray(w, float)
    z = (X - mu) / sd * w
    dbar = float(pdist(z).mean())
    if not dbar > 0:
        raise ValueError("every training point has the same weighted predictor values; the DI is undefined")
    return DISpace(mu, sd, w, z, dbar)


def training_di(space: DISpace, folds: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """Each training point's distance to the nearest training point of the other folds, / ``space.dbar``."""
    di = np.full(len(space.z), np.nan)
    for tr, va in folds:
        if len(tr) == 0:
            raise ValueError("a CV fold leaves no training points (the sites lie in a single block)")
        di[va] = nearest_distance(space.z[va], space.z[tr]) / space.dbar
    if np.isnan(di).any():
        raise ValueError("the CV folds do not hold out every training point")
    return di


def cv_folds(train: pd.DataFrame, cv: dict) -> list[tuple[np.ndarray, np.ndarray]]:
    return list(block_folds(train.lon.to_numpy(float), train.lat.to_numpy(float), cv["seed"], cv["block_deg"],
                            cv["folds"]))


def threshold(train_di: np.ndarray, rule: dict) -> dict:
    """The DI threshold of a rule (module docstring) with its diagnostics; ``value`` is the threshold."""
    kind = rule["rule"]
    if kind == "quantile":
        return {"value": float(np.quantile(train_di, rule["q"]))}
    if kind not in ("whisker", "fence_capped"):
        raise ValueError(f"unknown threshold rule {kind!r}; implemented: {list(RULES)}")
    q1, q3 = np.quantile(train_di, rule["quantiles"])
    fence = q3 + rule["iqr_multiplier"] * (q3 - q1)
    top = float(train_di.max())
    value = train_di[train_di <= fence].max() if kind == "whisker" else min(fence, top)
    return {"value": float(value), "fence": float(fence), "n_train_above_fence": int((train_di > fence).sum()),
            "train_di_max": top}


# ---------------------------------------------------------------- grid domains and shares

def lat_bands(lat: np.ndarray, bands: dict) -> np.ndarray:
    """Band label of each latitude (intervals (lower, upper], the first one closed)."""
    b = pd.cut(pd.Series(np.asarray(lat, float)), bins=list(bands["edges"]), labels=list(bands["labels"]), right=True,
               include_lowest=True)
    if b.isna().any():
        raise ValueError("phase2.aoa.lat_bands: some grid cells lie outside the band edges")
    return b.astype(str).to_numpy(object)


def ice_sheet_mask(cfg: Config, grid: pd.DataFrame, spec: dict) -> tuple[np.ndarray, dict]:
    """Cells of the ice sheets (module docstring) and the number found by each criterion."""
    by_cont = grid.continent_geo.isin(spec["continent_geo"]).to_numpy()
    south = grid.lat.to_numpy(float) < spec["south_of_lat"]
    ice = by_cont | south
    counts = {"continent_geo": int(by_cont.sum()), "south_of_lat": int(south.sum()),
              "continent_geo_or_south_of_lat": int(ice.sum()), "subunits": {}}
    names = list(spec["subunits"])
    if names:
        su = subunits(cfg)
        named = su[su.SUBUNIT.isin(names)]
        unknown = sorted(set(names) - set(named.SUBUNIT))
        if unknown:
            raise ValueError(f"phase2.aoa.ice_sheets.subunits: {unknown} are not Natural Earth map subunits")
        if named.ADMIN.eq("Russia").any():
            raise ValueError("phase2.aoa.ice_sheets.subunits: subunits of Russia are not supported (mshi.geo gives "
                             "Russian cells their continent by longitude)")
        # a cell matched to subunit S carries S's continent_geo (mshi.geo), so only those cells are looked up
        cand = np.flatnonzero(~ice & grid.continent_geo.isin(sorted(set(named.continent_geo))).to_numpy())
        sub = (geographic_continent(cfg, grid.lon.to_numpy(float)[cand], grid.lat.to_numpy(float)[cand], su)
               .geo_subunit.to_numpy(object) if len(cand) else np.array([], object))
        counts["n_cells_looked_up"] = int(len(cand))
        for n in names:
            hit = cand[sub == n]
            ice[hit] = True
            counts["subunits"][n] = int(len(hit))
            if not len(hit):
                log.warning("ice sheet subunit %r: no grid cell found", n)
    counts["n_cells"] = int(ice.sum())
    return ice, counts


def shares(outside: np.ndarray, area: np.ndarray, flux: np.ndarray) -> dict:
    """Shares of land area and of predicted flux outside the AOA among the given cells (None if they sum to 0)."""
    a, f = float(area.sum()), float(flux.sum())
    return {"n_cells": int(outside.size), "n_cells_outside": int(outside.sum()),
            "area_frac_outside": float(area[outside].sum() / a) if a > 0 else None,
            "flux_frac_outside": float(flux[outside].sum() / f) if f > 0 else None}


def domain_shares(outside: np.ndarray, area: np.ndarray, flux: np.ndarray, groups: dict[str, np.ndarray]) -> dict:
    """``shares`` overall and within each grouping (name -> label per cell), groups in sorted order."""
    out = shares(outside, area, flux)
    for gname, lab in groups.items():
        out[gname] = {g: shares(outside[lab == g], area[lab == g], flux[lab == g]) for g in sorted(set(lab))}
    return out


def domain_areas(area: np.ndarray, groups: dict[str, np.ndarray]) -> dict:
    out = {"n_cells": int(area.size), "area_km2": float(area.sum())}
    for gname, lab in groups.items():
        out[gname] = {g: {"n_cells": int((lab == g).sum()), "area_km2": float(area[lab == g].sum())}
                      for g in sorted(set(lab))}
    return out


def smearing_factor(y: np.ndarray, fitted: np.ndarray) -> float:
    """Duan (1983): mean of exp(residual) of the log-scale model."""
    return float(np.mean(np.exp(np.asarray(y, float) - np.asarray(fitted, float))))


# ---------------------------------------------------------------- transfer check

def r2(y: np.ndarray, p: np.ndarray) -> float:
    """1 - SSE/SST about the mean of ``y``; a zero SST gives 1 if SSE is 0, else 0 (scikit-learn's r2_score)."""
    sse = float(np.sum((y - p) ** 2))
    sst = float(np.sum((y - np.mean(y)) ** 2))
    if sst == 0:
        return 1.0 if sse == 0 else 0.0
    return 1.0 - sse / sst


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def subset_metrics(y: np.ndarray, p: np.ndarray, lon: np.ndarray, lat: np.ndarray, boot: dict) -> dict:
    """n, r2, rmse_log and their spatial-block bootstrap CIs (r2 and CIs need at least 2 sites)."""
    out: dict = {"n": int(len(y))}
    if len(y) == 0:
        return out
    out["rmse_log"] = rmse(y, p)
    if len(y) >= 2:
        out["r2"] = r2(y, p)
        kw = dict(n=boot["n"], seed=boot["seed"], lon=lon, lat=lat, deg=boot["block_deg"], q=boot["quantiles"])
        out["ci_r2"] = bootstrap_ci(y, p, stat=r2, **kw)
        out["ci_rmse_log"] = bootstrap_ci(y, p, stat=rmse, **kw)
    return out


# ---------------------------------------------------------------- one training set

@dataclass
class TrainedSet:
    name: str
    sites: pd.DataFrame
    model: object
    smear: float
    spaces: dict          # weights -> DISpace
    train_di: dict        # weights -> training DI
    info: dict


def train_set(cfg: Config, name: str, sites: pd.DataFrame) -> TrainedSet:
    p2, A = cfg["phase2"], cfg["phase2"]["aoa"]
    T, c8 = p2["target"], list(p2["c8"])
    sub = sites[sites.continent_geo.isin(train_continents(name, p2["continents"]))].reset_index(drop=True)
    X32 = sub[c8].to_numpy("float32")
    X, y = X32.astype(float), sub[T].to_numpy(float)
    model = fit_xgb(cfg, X32, y)
    smear = smearing_factor(y, model.predict(X32))
    folds = cv_folds(sub, A["cv"])
    spaces, tdi, weights = {}, {}, {}
    for wk in A["weights"]:
        w, fallback = importance_weights(wk, model, X, y, A["perm_repeats"], A["perm_seed"])
        spaces[wk] = di_space(X, w)
        tdi[wk] = training_di(spaces[wk], folds)
        weights[wk] = {"values": dict(zip(c8, w.tolist())), "fallback_equal": fallback, "dbar": spaces[wk].dbar,
                       "train_di_median": float(np.median(tdi[wk])), "train_di_max": float(tdi[wk].max())}
    info = {"continents": train_continents(name, p2["continents"]), "n_sites": int(len(sub)),
            "by_continent_geo": {c: int(v) for c, v in sorted(sub.continent_geo.value_counts().items())},
            "smearing_factor": smear, "cv": {"n_folds": len(folds), "fold_sizes": [int(len(va)) for _, va in folds]},
            "weights": weights}
    return TrainedSet(name, sub, model, smear, spaces, tdi, info)


def transfer_check(cfg: Config, sites: pd.DataFrame, ts: TrainedSet, thresholds: dict) -> dict:
    """The named continent's sites scored by the model of ``ts``, inside vs outside each of its AOA variants."""
    p2, A = cfg["phase2"], cfg["phase2"]["aoa"]
    T, c8, boot = p2["target"], list(p2["c8"]), p2["bootstrap"]
    test = A["transfer_check"]["test"]
    te = sites[sites.continent_geo == test].reset_index(drop=True)
    if te.site_id.isin(ts.sites.site_id).any():
        raise ValueError(f"transfer_check: {test} sites are in the training set {ts.name!r}")
    X32 = te[c8].to_numpy("float32")
    y, p = te[T].to_numpy(float), ts.model.predict(X32).astype(float)
    lon, lat = te.lon.to_numpy(float), te.lat.to_numpy(float)
    out = {"train": ts.name, "test": test, "exploratory": True, "all_sites": subset_metrics(y, p, lon, lat, boot),
           "variants": []}
    di = {wk: ts.spaces[wk].di(X32.astype(float)) for wk in A["weights"]}
    for th in A["thresholds"]:
        for wk in A["weights"]:
            v = thresholds[(ts.name, wk, th)]["value"]
            inside = di[wk] <= v
            out["variants"].append({
                "threshold": th, "weights": wk, "threshold_value": v,
                "frac_inside": float(inside.mean()) if len(inside) else None,
                "inside": subset_metrics(y[inside], p[inside], lon[inside], lat[inside], boot),
                "outside": subset_metrics(y[~inside], p[~inside], lon[~inside], lat[~inside], boot)})
    return out


# ---------------------------------------------------------------- figures

def _raster(lon: np.ndarray, lat: np.ndarray, values: np.ndarray, deg: float) -> np.ndarray:
    """Values of the cells of the regular ``deg`` grid (climate_grid's cell centres) as a (lat, lon) array; NaN for
    cells not in the grid."""
    n_lon, n_lat = int(round(360 / deg)), int(round(180 / deg))
    ix = np.rint((np.asarray(lon, float) + 180.0) / deg - 0.5).astype(int)
    iy = np.rint((np.asarray(lat, float) + 90.0) / deg - 0.5).astype(int)
    if ix.min() < 0 or ix.max() >= n_lon or iy.min() < 0 or iy.max() >= n_lat:
        raise ValueError("grid cells outside the globe")
    a = np.full((n_lat, n_lon), np.nan)
    a[iy, ix] = values
    return a


def _frame(ax, grid: pd.DataFrame, deg: float) -> None:
    ax.set_xlim(-180, 180)
    ax.set_ylim(max(-90.0, grid.lat.min() - deg / 2), min(90.0, grid.lat.max() + deg / 2))
    ax.set_aspect("equal")
    ax.set_xticks(range(-180, 181, 60))
    ax.set_yticks(range(-90, 91, 30))
    ax.tick_params(length=2, width=0.5)
    for s in ax.spines.values():
        s.set_linewidth(0.5)


def _label(train: str) -> str:
    return "all continents" if train == TRAIN_ALL else train


def di_map_figure(cfg: Config, grid: pd.DataFrame, di: np.ndarray, thr: float, primary: tuple[str, str, str],
                  sites: pd.DataFrame) -> list[Path]:
    from ..figures.style import PALETTE, save_figure
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D

    deg = cfg["phase2"]["aoa"]["grid_deg"]
    train, th, wk = primary
    lon, lat = grid.lon.to_numpy(float), grid.lat.to_numpy(float)
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    cmap = ListedColormap(plt.get_cmap("Blues")(np.linspace(0.12, 1.0, 256)))   # one hue, light -> dark
    im = ax.imshow(_raster(lon, lat, di, deg), origin="lower", extent=(-180, 180, -90, 90), cmap=cmap, vmin=0.0,
                   vmax=DI_VMAX_FACTOR * thr, interpolation="nearest")
    inside = _raster(lon, lat, (di <= thr).astype(float), deg)
    if np.nanmin(inside) < 0.5 < np.nanmax(inside):
        n_lat, n_lon = inside.shape
        ax.contour(-180 + deg * (np.arange(n_lon) + 0.5), -90 + deg * (np.arange(n_lat) + 0.5), inside, levels=[0.5],
                   colors=PALETTE["vermillion"], linewidths=0.6)
    ax.scatter(sites.lon, sites.lat, s=0.6, c=PALETTE["black"], linewidths=0)
    _frame(ax, grid, deg)
    ax.set_xlabel("longitude (°)")
    ax.set_ylabel("latitude (°)")
    cb = fig.colorbar(im, ax=ax, extend="max", shrink=0.75, pad=0.015)
    cb.set_label("dissimilarity index (DI)")
    cb.outline.set_linewidth(0.5)
    handles = [Line2D([], [], color=PALETTE["vermillion"], lw=0.8, label=f"AOA boundary ({th}: DI = {thr:.3f})"),
               Line2D([], [], color=PALETTE["black"], marker="o", ls="", ms=2, label=f"training sites (n = {len(sites)})")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False)
    ax.set_title(f"DI of the {deg}° land grid: XGB on c8 trained on {_label(train)}, {wk} weights (exploratory)")
    return save_figure(fig, cfg.path("figures", "phase2", "aoa_di_map"))


def variants_figure(cfg: Config, grid: pd.DataFrame, inside: dict, variants: list[dict]) -> list[Path]:
    from ..figures.style import PALETTE, save_figure
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    A = cfg["phase2"]["aoa"]
    deg = A["grid_deg"]
    lon, lat = grid.lon.to_numpy(float), grid.lat.to_numpy(float)
    rows = [(t, th) for t in A["train"] for th in A["thresholds"]]
    cols = list(A["weights"])
    fig, axes = plt.subplots(len(rows), len(cols), figsize=(3.6 * len(cols), 2.0 * len(rows) + 0.6), squeeze=False,
                             layout="constrained")
    cmap = ListedColormap([PALETTE["vermillion"], PALETTE["sky"]])          # 0 = outside, 1 = inside
    by_key = {(v["train"], v["threshold"], v["weights"]): v for v in variants}
    for i, (t, th) in enumerate(rows):
        for j, wk in enumerate(cols):
            ax, v = axes[i, j], by_key[(t, th, wk)]
            ax.imshow(_raster(lon, lat, inside[(t, wk, th)].astype(float), deg), origin="lower",
                      extent=(-180, 180, -90, 90), cmap=cmap, vmin=0.0, vmax=1.0, interpolation="nearest")
            _frame(ax, grid, deg)
            ax.tick_params(labelbottom=i == len(rows) - 1, labelleft=j == 0)
            a, b = (v[d]["area_frac_outside"] for d in DOMAINS)
            ax.set_title(f"{_label(t)} | {th} (DI {v['threshold_value']:.3f}) | {wk}\n"
                         f"outside: {a:.1%} of land, {b:.1%} without ice sheets", fontsize=7)
    fig.legend(handles=[Patch(color=PALETTE["sky"], label="inside the AOA"),
                        Patch(color=PALETTE["vermillion"], label="outside the AOA")],
               loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("AOA of XGB on c8: training set x threshold (rows) x importance weights (columns); exploratory",
                 fontsize=9)
    return save_figure(fig, cfg.path("figures", "phase2", "aoa_variants"))


# ---------------------------------------------------------------- stage

def aoa_sensitivity(cfg: Config) -> dict:
    p2 = cfg["phase2"]
    A = aoa_settings(cfg)
    c8 = list(p2["c8"])
    sites, site_info = analysis_sites(cfg)
    grid = climate_grid(cfg, A["grid_deg"])
    lon, lat = grid.lon.to_numpy(float), grid.lat.to_numpy(float)
    area = grid.area_km2.to_numpy(float)
    G32 = grid[c8].to_numpy("float32")
    G = G32.astype(float)
    cont = grid.continent_geo.astype(object).where(grid.continent_geo.notna(), UNASSIGNED).to_numpy(object)
    band = lat_bands(lat, A["lat_bands"])
    ice, ice_counts = ice_sheet_mask(cfg, grid, A["ice_sheets"])
    keep = {"all_land": np.ones(len(grid), bool), "excluding_ice_sheets": ~ice}

    table = pd.DataFrame({"lon": lon, "lat": lat, "area_km2": area, "continent_geo": cont, "lat_band": band,
                          "ice_sheet": ice})
    trained, thresholds, inside, variants = {}, {}, {}, []
    for t in A["train"]:
        ts = trained[t] = train_set(cfg, t, sites)
        pred = ts.model.predict(G32).astype(float)
        flux = np.exp(pred) * ts.smear * area
        table[f"pred_log_{_slug(t)}"] = pred
        for wk in A["weights"]:
            di = ts.spaces[wk].di(G)
            table[f"di_{_slug(t)}_{wk}"] = di
            for th in A["thresholds"]:
                thr = thresholds[(t, wk, th)] = threshold(ts.train_di[wk], A["threshold_rules"][th])
                ins = inside[(t, wk, th)] = di <= thr["value"]
                table[f"aoa_{_slug(t)}_{th}_{wk}"] = ins
                v = {"train": t, "threshold": th, "weights": wk, "threshold_value": thr["value"],
                     "threshold_detail": {k: x for k, x in thr.items() if k != "value"},
                     "train_frac_above_threshold": float(np.mean(ts.train_di[wk] > thr["value"]))}
                for dom, m in keep.items():
                    v[dom] = domain_shares(~ins[m], area[m], flux[m], {"by_continent_geo": cont[m],
                                                                       "by_lat_band": band[m]})
                variants.append(v)
    # variants in config order: training set, then threshold, then weights
    order = {(t, th, wk): i for i, (t, th, wk) in enumerate((t, th, wk) for t in A["train"] for th in A["thresholds"]
                                                            for wk in A["weights"])}
    variants.sort(key=lambda v: order[(v["train"], v["threshold"], v["weights"])])
    check = transfer_check(cfg, sites, trained[A["transfer_check"]["train"]], thresholds)

    primary = (A["train"][0], A["thresholds"][0], A["weights"][0])
    table_path = write_table(table, cfg.path("interim", "aoa_di_grid.parquet"))
    figs = di_map_figure(cfg, grid, table[f"di_{_slug(primary[0])}_{primary[2]}"].to_numpy(float),
                         thresholds[(primary[0], primary[2], primary[1])]["value"], primary, trained[primary[0]].sites)
    figs += variants_figure(cfg, grid, inside, variants)
    groups = {"by_continent_geo": cont, "by_lat_band": band}
    res = {"exploratory": True, "method": method_text(cfg), "variant": p2["variant"], "target": p2["target"],
           "continent_column": "continent_geo", "predictors": c8, "settings": A,
           "xgb": {**cfg["clean_test"]["locked"]["xgb"], "random_state": p2["transfer"]["xgb_seed"],
                   "from": "clean_test.locked.xgb"},
           "bootstrap": p2["bootstrap"], "versions": _versions(), "sites": site_info,
           "grid": {"deg": A["grid_deg"], "ice_sheets": ice_counts,
                    "n_cells_unassigned_continent": int((cont == UNASSIGNED).sum()),
                    "domains": {dom: domain_areas(area[m], {g: lab[m] for g, lab in groups.items()})
                                for dom, m in keep.items()}},
           "training_sets": {t: trained[t].info for t in A["train"]},
           "primary_variant": dict(zip(("train", "threshold", "weights"), primary)),
           "variants": variants, "transfer_check": check, "grid_table": cfg.root_key(table_path),
           "notes": ["exploratory (brief section 5); the training set 'all' includes Europe and North America, and "
                     "nothing here feeds back into the locked test (ground rules 4 and 5)",
                     "no global Rs total is reported (F-H25); flux shares use exp(prediction) x Duan smearing x cell "
                     "area, and the smearing factor cancels in every share",
                     "ice sheets: continent_geo in ice_sheets.continent_geo, or cell centre south of "
                     "ice_sheets.south_of_lat, or Natural Earth map subunit in ice_sheets.subunits "
                     "(mshi.geo.geographic_continent); counts in grid.ice_sheets",
                     "barren land is not removed (no land cover in Phase 2); cell areas are whole lon/lat cells",
                     "CAST 1.2.0's threshold is min(fence, train_di_max) (threshold_detail of the whisker rule), "
                     "the brief's and the handoff's is the outlier-removed maximum (whisker_max)"]}
    write_result(cfg, res, "aoa_sensitivity.json", outputs=[table_path, *figs],
                 inputs=["features_analysis.json", "fetch_worldclim.json"])
    first = variants[0]
    return {"primary": {"train": first["train"], "threshold": first["threshold"], "weights": first["weights"],
                        "area_frac_outside": first["all_land"]["area_frac_outside"],
                        "area_frac_outside_excluding_ice_sheets": first["excluding_ice_sheets"]["area_frac_outside"]},
            "n_variants": len(variants), "n_train": {t: trained[t].info["n_sites"] for t in A["train"]}}
