"""Why the original US R² was low: the handoff's E4 and E4b re-run cleanly (Phase 2, brief section 5 item 5;
exploratory). Replaces docs/handoff/scripts/exp_ablation.py (E4) and exp_ablation2.py (E4b) and answers the critique
of them (docs/DECISIONS.md F-H21: the xgboost version; F-H22: E4's "site mean vs single record: no change" holds for
continents only; F-H29: E4/E4b do not reproduce the original configuration and do not name their filter set).

Stage ``us_r2``. For every site-build variant (``site_build.variants``), target, training region, learner and test
region, the learner is fitted on the training region's sites and scored on the test region's sites.

Inputs
- Sites: data/interim/features_analysis_<variant>.parquet, recorded outputs of a current ``features_analysis``
  result (the analysis build: geodesic coordinate check, restricted COSORE, D-P2-1/D-P2-2). Variants and their filter
  sets (named in the result, F-H29): qc = repository filters + coordinate check + QC filters (``phase2.variant``, the
  primary); repo = repository filters + coordinate check only (the filter set of E4 and E4b). A site is used if the
  target, its coordinates and every predictor of every learner are present and the log-entered predictors are
  positive, so both learners and both targets are scored on the same sites. Sites are sorted by ``site_id`` first, so
  results do not depend on the table's row order.
- Records: data/derived/records_analysis.parquet, a recorded output of a current ``build_sites_analysis`` result,
  mapped to sites by ``site_id_<variant>``. Every used site must have its records, whose count and mean log Rs equal
  the site's ``n_rec`` and target (refused otherwise: the tables would not belong together). Records of sites that
  are not used (incomplete features; smoke subsets) are left out and counted.

Regions (``phase2.us_r2``). Continents are geographic (``continent_geo``: overseas territories by location, D-P2-3),
never the locked ``continent`` column. Boxes are [lon0, lon1, lat0, lat1] on the site coordinates (the mean of the
site's record coordinates), closed intervals (lon0 <= lon <= lon1 and lat0 <= lat <= lat1, as pandas ``between`` in
E4/E4b), whatever the continent; a box must not cross the antimeridian (refused).
- Training: ``train_continent`` (Asia) by geographic continent, and ``asia_box``, the original (v1/v2) training box,
  which also holds European, African and Oceanian sites, as the original table did (F-H2).
- Test: ``us_box``, the original "US" (CONUS) box, called the "US bounding box" here because it also holds southern
  Canadian and Mexican sites (F-H29); ``test_continent`` (North America) by geographic continent; and the test
  continent outside the US bounding box. A test site that is also a training site (e.g. a western-Aleutian site, in
  North America and in the Asia box) is excluded from that row's test set; overlaps are counted and listed.

Targets (training and test use the same one)
- ``site_mean``: the site's mean log Rs over its records (``phase2.target`` of the site table; the v3 target).
- ``single_record``: the log Rs of one record per site, chosen by the original (v1/v2) de-duplication rule as E4 did:
  a COSORE record first, else the SRDB record with the lowest CSV row number (parsed from ``rec_id`` = ``srdb_<row>``
  as a number, and checked against the ``srdb_row`` column when the table has one). The rule does not order several
  COSORE records at one site (E4 kept its table order); here the lowest ``rec_id`` is taken, so the choice does not
  depend on the table's row order.
Both targets use the same sites and the same features (sampled at the site's coordinates by features_analysis).

Learners (``us_r2.learners``)
- XGB: ``xgboost.XGBRegressor(**<the block named by phase2.transfer.xgb_from>, random_state=phase2.transfer.xgb_seed)``
  on ``phase2.c8`` (float32, as LockedTest and mshi.analysis.transfer; the block is the locked ``clean_test.locked.xgb``
  and comes from ``transfer.xgb_block``, so the row this stage shares with transfer_matrix cannot differ). Refitted with every seed of ``us_r2.xgb_seed_spread``
  (inclusive range; the fit with ``xgb_seed`` is reused) to report the range and mean over seeds of r2 and rmse_log
  next to each row, and of the target effect's r2 difference (E4 reported a 5-seed mean; the critique's verifier found
  seed 0 to be a high draw for E4's single-record box row, F-H22). Library versions are recorded (F-H21).
- OLS-TP: least squares on bio01 and ln bio12 (``phase2.transfer.ols_tp``, the locked form).

Metrics (log Rs of the test sites of a row unless stated)
- r2 = 1 - SSE/SST, SST about the test-set mean (scikit-learn's ``r2_score``; a zero SST gives 1 if SSE is 0, else 0).
- rmse_log; sd_log = the test sites' SD about their mean with divisor n, so r2 = 1 - (rmse_log / sd_log)^2: R²
  compares the model's error with the test set's spread, so a test region with a small spread gives a small R² for
  the same error (E4b's point; E4b's ``test_sd`` used divisor n - 1).
- The intercept-only prediction is the training set's mean target: rmse_null_log (rmse_null_log^2 = sd_log^2 +
  null_bias_log^2), skill_vs_train_mean = 1 - MSE/MSE_null (MSE scale, as mshi.analysis.transfer; it rewards fixing
  the offset between regions, F-H24, so read it with null_bias_log), bias_log = mean(prediction - observation),
  null_bias_log = mean(training mean - observation).
- rmse_rs and rmse_null_rs in g C m-2 yr-1 after a plain exp() back-transform of prediction and observation (no
  smearing, as LockedTest.metrics).
- CIs: spatial-block bootstrap of the test sites with the draws of ``mshi.spatial.bootstrap_ci``
  (``phase2.bootstrap``: block_deg-degree blocks resampled with replacement, n replicates, the generator re-seeded for
  every test set, percentile intervals at ``quantiles``; mshi.analysis.transfer.block_replicates); every metric is
  recomputed on each replicate. Rows scored on the same sites share their replicates, so the target effect (r2 and
  rmse_log of the site-mean target minus those of the single-record target; same variant, regions and learner) has a
  paired CI. The CIs are conditional on the fitted models: training sites are not resampled (as F-H6 notes for the
  locked test). Rows whose test set has fewer than ``phase2.min_test_sites`` sites are flagged; a training set with
  fewer sites than that is not fitted (recorded, as mshi.analysis.transfer).

Outputs: results/us_r2.json (rows, target effects, the filter set, site counts, single-record summary, region
composition and overlaps of each variant, library versions) and figure phase2/us_r2 (R² and RMSE with CIs for the US
bounding box, the test continent and the test continent outside the box, per training region, learner and variant;
site-mean target; the test-set SD drawn next to each RMSE).

Differences from E4/E4b: the analysis site build (geodesic coordinate check, restricted COSORE) instead of the locked
one; geographic continents (E4/E4b used the locked country rule, which put Hawaii in North America); features at the
site's mean coordinates for both targets (E4: at the chosen record's coordinates, for both targets); both filter sets,
named (E4/E4b: repo only, unnamed); both learners (E4/E4b: XGB only); CIs for every metric from a block bootstrap
seeded per test set (E4: a site bootstrap of r2 only, from one generator shared by all rows, so each CI depends on the
rows before it; E4b: none); test sites that are training sites excluded and reported (E4/E4b did not check: the two
boxes do not intersect, but the Asia box and North America can, at the western Aleutians); the pinned xgboost 2.1.4
(the handoff README says E4 ran under 3.4.1); the test-set SD with divisor n (E4b: n - 1).

Not the original configuration (F-H29): the original (v1/v2) pipeline kept one record per 0.05-degree cell (COSORE
first, then the lowest SRDB row) without QC filters or a coordinate check, used 66 COSORE sites and sampled WorldClim
at 10 arc-min (docs/handoff/prep_log.md sections 3 and 5; the critique's replication of its de-duplication). Here
the site unit is the v3 5-km cluster and WorldClim is 2.5', so no variant reproduces the original 615 training and
274 test sites. E4's rows on the original 889 sites with their original features are not re-run here.

Limits. Exploratory (brief section 5): North America is used for exploratory analyses only (ground rule 5). The
Asia box holds sites of the locked Europe test set (F-H2); training on them here does not touch the locked test
(ground rule 4). Regions are compared on different site sets, so differences between test regions have no paired
CI; only the target effect is paired. One XGB seed defines each row; the seed spread is reported next to it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from ..config import Config
from ..io import read_table, require_outputs, write_result
from .transfer import Replicates, block_replicates, ci, design, xgb_block

log = logging.getLogger("mshi.us_r2")

KEYS = ("asia_box", "us_box", "learners", "train_continent", "test_continent", "xgb_seed_spread")   # phase2.us_r2
LEARNERS = ("XGB", "OLS-TP")
TARGETS = ("site_mean", "single_record")
VARIANTS = ("qc", "repo")    # the filter sets mshi.data.sites_analysis builds (described by ``filter_sets``)
SOURCES = ("cosore", "srdb")
METRICS = ("r2", "rmse_log", "sd_log", "rmse_null_log", "skill_vs_train_mean", "bias_log", "null_bias_log", "rmse_rs",
           "rmse_null_rs")
EFFECT_METRICS = ("r2", "rmse_log")
SPREAD_METRICS = ("r2", "rmse_log")
BOX_TRAIN = "Asia box"
BOX_TEST = "US bounding box"
UPSTREAM = ("features_analysis.json", "build_sites_analysis.json")
SRDB_ID = re.compile(r"^srdb_(\d+)$")
MEAN_ATOL = 1e-9             # numerical slack: site-table target vs the mean of the site's records
N_EXAMPLES = 10              # how many overlapping or unmatched sites a result lists
R2_FLOOR = -1.0              # display only: lower end of the R² axis (lower values are drawn on it and labelled)


# ---------------------------------------------------------------- configuration

def check_box(name: str, box: list | tuple) -> tuple[float, float, float, float]:
    """``box`` as (lon0, lon1, lat0, lat1); refuses anything else, and boxes crossing the antimeridian."""
    b = tuple(float(v) for v in box)
    if len(b) != 4 or not (-180.0 <= b[0] < b[1] <= 180.0 and -90.0 <= b[2] < b[3] <= 90.0):
        raise ValueError(f"phase2.us_r2.{name} must be [lon0, lon1, lat0, lat1] with -180 <= lon0 < lon1 <= 180 and "
                         f"-90 <= lat0 < lat1 <= 90 (a box may not cross the antimeridian), got {list(box)}")
    return b


@dataclass(frozen=True)
class Settings:
    """Everything that defines the stage (module docstring), read from the config and checked."""
    variants: tuple[str, ...]
    primary: str
    target: str
    c8: tuple[str, ...]
    ols_tp: dict
    xgb: dict
    xgb_from: str
    xgb_seed: int
    seed_spread: tuple[int, int]
    learners: tuple[str, ...]
    train_continent: str
    test_continent: str
    asia_box: tuple[float, float, float, float]
    us_box: tuple[float, float, float, float]
    bootstrap: dict
    min_sites: int

    @classmethod
    def from_cfg(cls, cfg: Config) -> Settings:
        p2 = cfg["phase2"]
        U = p2.get("us_r2") or {}
        missing = [k for k in KEYS if k not in U]
        if missing:
            raise ValueError(f"phase2.us_r2 lacks {missing} (the settings mshi/analysis/us_r2.py reads)")
        learners = list(U["learners"])
        if not learners or len(set(learners)) != len(learners) or any(x not in LEARNERS for x in learners):
            raise ValueError(f"phase2.us_r2.learners must name distinct implemented learners {list(LEARNERS)}, got "
                             f"{learners}")
        for k in ("train_continent", "test_continent"):
            if U[k] not in p2["continents"]:
                raise ValueError(f"phase2.us_r2.{k} {U[k]!r} is not one of phase2.continents")
        if U["train_continent"] == U["test_continent"]:
            raise ValueError("phase2.us_r2: train_continent and test_continent must differ")
        spread = [int(s) for s in U["xgb_seed_spread"]]
        if len(spread) != 2 or spread[0] > spread[1]:
            raise ValueError(f"phase2.us_r2.xgb_seed_spread must be [first, last] seeds, got {U['xgb_seed_spread']}")
        lo, hi = spread
        variants = tuple(cfg["site_build"]["variants"])
        if any(v not in VARIANTS for v in variants) or p2["variant"] not in variants:
            raise ValueError(f"site_build.variants {list(variants)} must be among {list(VARIANTS)} (the filter sets "
                             f"this stage can name) and include phase2.variant {p2['variant']!r}")
        xgb, xgb_from = xgb_block(cfg)
        return cls(variants=variants, primary=p2["variant"], target=p2["target"], c8=tuple(p2["c8"]),
                   ols_tp=dict(p2["transfer"]["ols_tp"]), xgb=xgb, xgb_from=xgb_from,
                   xgb_seed=int(p2["transfer"]["xgb_seed"]), seed_spread=(lo, hi), learners=tuple(learners),
                   train_continent=U["train_continent"], test_continent=U["test_continent"],
                   asia_box=check_box("asia_box", U["asia_box"]), us_box=check_box("us_box", U["us_box"]),
                   bootstrap=dict(p2["bootstrap"]), min_sites=int(p2["min_test_sites"]))

    def predictors(self) -> list[str]:
        """Every predictor any learner uses, in a fixed order."""
        return list(dict.fromkeys([*self.c8, *self.ols_tp["features"]]))

    def seeds(self) -> list[int]:
        return list(range(self.seed_spread[0], self.seed_spread[1] + 1))

    def describe(self) -> dict:
        return {"XGB": {**self.xgb, "random_state": self.xgb_seed, "features": list(self.c8),
                        "from": self.xgb_from, "seed_spread": list(self.seed_spread)},
                "OLS-TP": {**self.ols_tp, "from": "phase2.transfer.ols_tp"}}


def filter_sets(cfg: Config) -> dict[str, str]:
    """The filter set of each variant (F-H29), from the settings mshi.data.sites_analysis applies."""
    sb, co = cfg["site_build"], cfg["cosore_analysis"]
    q, cc = sb["qc"], sb["coord_check"]
    lo, hi = sb["rs_range"]
    repo = (f"repository filters: SRDB records with coordinates and {lo:g} <= Rs_annual <= {hi:g} g C m-2 yr-1, "
            f"Manipulation in {sb['manipulation_keep']} or missing; COSORE ports with CSR_MSMT_VAR {co['msmt_var']}, "
            f"treatment {co['treatment']!r} and full-year coverage (cosore_analysis, D-P2-1), annual values in the "
            f"same Rs range. Coordinate check (geodesic, D-P2-2): SRDB records more than {cc['max_km']:g} km from "
            f"their reported country dropped "
            f"(site_build.coord_check aliases and territory exceptions), and records with no country or geographic "
            f"continent within {sb['continent']['nearest_max_m'] / 1000:g} km dropped. Sites: records within "
            f"{sb['merge_radius_km']:g} km merged (connected components), at the mean of their coordinates")
    qc = (f"{repo}. QC filters: records dropped if Meas_method matches '{q['method_regex']}' (case-insensitive), "
          f"Quality_flag matches '{q['quality_regex']}', Annual_coverage < {q['min_annual_coverage']:g}, "
          f"Ecosystem_type is in {q['ecosystem_exclude']} (COSORE IGBP {q['cosore_ecosystem_exclude_upper']}), or "
          f"Duplicate_record is set")
    return {"qc": f"coordinate check + QC filters. {qc}", "repo": f"repository filters + coordinate check only (the "
            f"filter set of E4 and E4b). {repo}"}


def method_text(S: Settings) -> str:
    a, u, B = S.asia_box, S.us_box, S.bootstrap
    return (f"Train on {S.train_continent} (geographic continent) or the original Asia box (lon {a[0]:g} to "
            f"{a[1]:g}, lat {a[2]:g} to {a[3]:g}; any continent); test on the original US bounding box (lon {u[0]:g} "
            f"to {u[1]:g}, lat {u[2]:g} to {u[3]:g}; any continent), on {S.test_continent} (geographic) and on "
            f"{S.test_continent} outside that box; test sites that are training sites are excluded. Learners: XGB "
            f"({S.xgb_from}, random_state phase2.transfer.xgb_seed; seeds {S.seed_spread[0]}-"
            f"{S.seed_spread[1]} as a range) on c8, OLS-TP log Rs ~ bio01 + ln bio12. Targets: site-mean log Rs, and "
            f"one record per site by the original rule (COSORE first, then the lowest SRDB row), on the same sites and "
            f"features. Variants {list(S.variants)} (filter sets named under 'variants'). Metrics on log Rs of the "
            f"test sites: r2 (vs the test-set mean) = 1 - (rmse_log/sd_log)^2 with sd_log the test-set SD (divisor "
            f"n); the training-mean prediction's rmse_null_log and skill_vs_train_mean = 1 - MSE/MSE_null; biases; "
            f"rmse_rs and rmse_null_rs (g C m-2 yr-1, plain exp()). CIs: {B['block_deg']:g}-degree block bootstrap of "
            f"the test sites ({B['n']} replicates), conditional on the fitted models; the target effect (site mean "
            f"minus single record) is paired.")


def _versions() -> dict:
    import sklearn
    import xgboost
    return {"numpy": np.__version__, "pandas": pd.__version__, "scikit-learn": sklearn.__version__,
            "xgboost": xgboost.__version__}


# ---------------------------------------------------------------- regions

def in_box(lon: np.ndarray, lat: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Closed-interval box membership (pandas ``between`` in E4/E4b); NaN coordinates are outside."""
    lon0, lon1, lat0, lat1 = box
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return (lon >= lon0) & (lon <= lon1) & (lat >= lat0) & (lat <= lat1)


@dataclass(frozen=True)
class Region:
    """The sites of a geographic continent, of a box, of both, or of a continent outside a box."""
    name: str
    continent: str | None = None
    box: tuple[float, float, float, float] | None = None
    outside: tuple[float, float, float, float] | None = None

    def mask(self, d: pd.DataFrame) -> np.ndarray:
        lon, lat = d.lon.to_numpy(float), d.lat.to_numpy(float)
        m = np.ones(len(d), dtype=bool)
        if self.continent is not None:
            m &= d.continent_geo.eq(self.continent).to_numpy(dtype=bool, na_value=False)
        if self.box is not None:
            m &= in_box(lon, lat, self.box)
        if self.outside is not None:
            m &= ~in_box(lon, lat, self.outside)
        return m

    def describe(self) -> str:
        parts = [f"continent_geo == {self.continent!r}"] if self.continent is not None else []
        for word, b in (("inside", self.box), ("outside", self.outside)):
            if b is not None:
                parts.append(f"{word} {b[0]:g} <= lon <= {b[1]:g} and {b[2]:g} <= lat <= {b[3]:g}")
        return " and ".join(parts) + ("" if self.continent is not None else " (any continent)")


def regions(S: Settings) -> tuple[list[Region], list[Region]]:
    """(training regions, test regions), in reporting order."""
    train = [Region(S.train_continent, continent=S.train_continent), Region(BOX_TRAIN, box=S.asia_box)]
    test = [Region(BOX_TEST, box=S.us_box), Region(S.test_continent, continent=S.test_continent),
            Region(f"{S.test_continent} outside the {BOX_TEST}", continent=S.test_continent, outside=S.us_box)]
    return train, test


def _counts(s: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in s.astype(object).where(s.notna(), "missing").value_counts().items()}


def composition(d: pd.DataFrame, trains: list[Region], tests: list[Region]) -> dict:
    """Per region: the number of sites, by geographic continent, and (test regions) by country; for a region outside
    a box, where its sites lie relative to the box."""
    out = {}
    for r in trains + tests:
        m = r.mask(d)
        e = {"n": int(m.sum()), "by_continent_geo": _counts(d.continent_geo[m])}
        if r in tests:
            e["by_country"] = _counts(d.country[m])
        if r.outside is not None:
            lat = d.lat.to_numpy(float)[m]
            lat0, lat1 = r.outside[2], r.outside[3]
            e["relative_to_box"] = {"south": int((lat < lat0).sum()), "north": int((lat > lat1).sum()),
                                    "west_or_east": int(((lat >= lat0) & (lat <= lat1)).sum())}
            e["relative_to_box_definition"] = (f"south: lat < {lat0:g}; north: lat > {lat1:g}; west_or_east: within "
                                               f"the box's latitudes, outside its longitudes")
        out[r.name] = e
    return out


def overlaps(d: pd.DataFrame, trains: list[Region], tests: list[Region]) -> list[dict]:
    """Sites in both a training and a test region (excluded from that test set), per pair of regions."""
    out = []
    for tr in trains:
        for te in tests:
            m = tr.mask(d) & te.mask(d)
            ex = d.loc[m, ["site_id", "lon", "lat", "continent_geo"]].head(N_EXAMPLES)
            out.append({"train": tr.name, "test": te.name, "n": int(m.sum()),
                        "examples": [{"site_id": s, "lon": float(x), "lat": float(y), "continent_geo": c}
                                     for s, x, y, c in ex.itertuples(index=False)]})
    return out


# ---------------------------------------------------------------- sites and targets

def prepare_sites(raw: pd.DataFrame, S: Settings) -> tuple[pd.DataFrame, dict]:
    """The usable sites (module docstring), sorted by site_id, and the counts left out."""
    feats, T = S.predictors(), S.target
    cols = ["site_id", "lon", "lat", "continent_geo", "country", "n_rec", T] + feats
    missing = [c for c in cols if c not in raw]
    if missing:
        raise ValueError(f"features table lacks {missing}")
    d = raw[cols].copy()
    d["site_id"] = d.site_id.astype(str)
    if d.site_id.duplicated().any():
        raise ValueError("features table: site_id is not unique")
    complete = d[[T, "lon", "lat"] + feats].notna().all(axis=1)
    positive = (d[list(S.ols_tp["log"])] > 0).all(axis=1)
    keep = complete & positive
    info = {"n_table": int(len(d)), "n_used": int(keep.sum()), "n_missing_values": int((~complete).sum()),
            "n_nonpositive_log_predictor": int((complete & ~positive).sum())}
    return d[keep].sort_values("site_id", kind="mergesort").reset_index(drop=True), info


def srdb_rows(rec: pd.DataFrame) -> np.ndarray:
    """The SRDB CSV row of each SRDB record, from ``rec_id`` = ``srdb_<row>`` (checked against ``srdb_row`` when the
    table has that column); -1 for COSORE records."""
    srdb = rec.src.eq("srdb").to_numpy(dtype=bool, na_value=False)
    ids = rec.rec_id.astype(str).to_numpy()
    rows = np.full(len(rec), -1, dtype=np.int64)
    for i in np.flatnonzero(srdb):
        m = SRDB_ID.match(ids[i])
        if m is None:
            raise ValueError(f"SRDB record id {ids[i]!r} is not of the form srdb_<row>")
        rows[i] = int(m.group(1))
    if "srdb_row" in rec:
        bad = srdb & ~(rec.srdb_row.to_numpy(float) == rows)
        if bad.any():
            raise ValueError(f"{int(bad.sum())} SRDB records whose srdb_row differs from the row in their rec_id "
                             f"(e.g. {sorted(ids[bad])[:N_EXAMPLES]})")
    return rows


def single_record(rec: pd.DataFrame, d: pd.DataFrame, variant: str, target: str) -> tuple[pd.DataFrame, dict]:
    """For each site of ``d`` (in its order): the record chosen by the original rule (module docstring), with its
    ``rec_id``, ``src``, SRDB ``row`` and target value; and a summary. Refuses (ValueError) records that do not match
    the site table."""
    col = f"site_id_{variant}"
    missing = [c for c in ("rec_id", "src", target, col) if c not in rec]
    if missing:
        raise ValueError(f"records table lacks {missing}")
    r = rec[rec[col].notna()].copy()
    r["site_id"] = r[col].astype(str)
    src = r.src.astype(str)
    if not src.isin(SOURCES).all():
        raise ValueError(f"records with an unknown source: {sorted(set(src) - set(SOURCES))}")
    if r.rec_id.duplicated().any():
        raise ValueError("records table: rec_id is not unique")
    if not np.isfinite(r[target].to_numpy(float)).all():
        raise ValueError(f"records with a non-finite {target}")
    r["row"] = srdb_rows(r)
    r["cosore_first"] = np.where(src.eq("cosore").to_numpy(), 0, 1)
    known = r.site_id.isin(d.site_id)
    info = {"records_of_sites_not_used": int((~known).sum())}
    r = r[known]
    agg = r.groupby("site_id")[target].agg(["size", "mean"])
    chk = d.set_index("site_id")[["n_rec", target]].join(agg, how="left")
    if chk["size"].isna().any():
        none = sorted(chk.index[chk["size"].isna()])
        raise ValueError(f"{len(none)} sites have no record in the records table (e.g. {none[:N_EXAMPLES]})")
    bad = (chk["size"] != chk.n_rec) | ((chk["mean"] - chk[target]).abs() > MEAN_ATOL)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} sites whose record count or mean {target} differs from the site table "
                         f"(e.g. {sorted(chk.index[bad])[:N_EXAMPLES]})")
    first = (r.sort_values(["site_id", "cosore_first", "row", "rec_id"])
             .drop_duplicates("site_id", keep="first").set_index("site_id"))
    out = first.loc[d.site_id.to_numpy(), ["rec_id", "src", "row", target]].reset_index()
    several = d.n_rec.to_numpy() >= 2
    diff = np.abs(out[target].to_numpy(float) - d[target].to_numpy(float))
    info.update({"n_sites": int(len(out)), "n_chosen_cosore": int(out.src.eq("cosore").sum()),
                 "n_sites_with_several_records": int(several.sum()),
                 "n_sites_with_several_cosore_records": int((r.src.eq("cosore").groupby(r.site_id).sum() > 1).sum()),
                 "mean_abs_diff_from_site_mean_log": float(diff[several].mean()) if several.any() else 0.0,
                 "max_abs_diff_from_site_mean_log": float(diff.max()) if len(diff) else 0.0})
    return out, info


# ---------------------------------------------------------------- learners

def fit_predict(S: Settings, learner: str, train: pd.DataFrame, y: np.ndarray, d: pd.DataFrame,
                seed: int | None = None) -> tuple[np.ndarray, dict]:
    """Fit ``learner`` on ``train`` (targets ``y``) and predict every site of ``d``; ``seed`` replaces the XGB seed."""
    if learner == "OLS-TP":
        o = S.ols_tp
        lr = LinearRegression().fit(design(train, o["features"], o["log"]), y)
        names = [f"ln {c}" if c in o["log"] else c for c in o["features"]]
        return lr.predict(design(d, o["features"], o["log"])), {
            "intercept": float(lr.intercept_), "coef": dict(zip(names, map(float, lr.coef_)))}
    if learner == "XGB":
        import xgboost
        rs = S.xgb_seed if seed is None else seed
        m = xgboost.XGBRegressor(**S.xgb, random_state=rs).fit(train[list(S.c8)].to_numpy("float32"), y)
        return m.predict(d[list(S.c8)].to_numpy("float32")).astype(float), {"random_state": rs}
    raise ValueError(f"unknown learner {learner!r}")


# ---------------------------------------------------------------- metrics and the block bootstrap

def _skill(err: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """1 - err/ref; a zero ``ref`` gives 1 if ``err`` is 0, else 0 (scikit-learn's ``r2_score``)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        v = 1.0 - err / ref
    return np.where(ref > 0, v, np.where(err == 0, 1.0, 0.0))


def metric_arrays(y: np.ndarray, p: np.ndarray, base: np.ndarray, idx: np.ndarray, rep: np.ndarray,
                  n_rep: int) -> dict[str, np.ndarray]:
    """Every metric (module docstring) for each replicate: replicate ``rep[i]`` contains site ``idx[i]``; ``base`` is
    the intercept-only prediction (the training mean) of each site."""
    y, p, base = (np.asarray(a, float)[idx] for a in (y, p, base))

    def s(w: np.ndarray) -> np.ndarray:
        return np.bincount(rep, weights=w, minlength=n_rep)
    n = np.bincount(rep, minlength=n_rep).astype(float)
    sst = s((y - (s(y) / n)[rep]) ** 2)
    e, e0 = p - y, base - y
    sse, sse0 = s(e ** 2), s(e0 ** 2)
    ry = np.exp(y)
    return {"r2": _skill(sse, sst), "rmse_log": np.sqrt(sse / n), "sd_log": np.sqrt(sst / n),
            "rmse_null_log": np.sqrt(sse0 / n), "skill_vs_train_mean": _skill(sse, sse0), "bias_log": s(e) / n,
            "null_bias_log": s(e0) / n, "rmse_rs": np.sqrt(s((np.exp(p) - ry) ** 2) / n),
            "rmse_null_rs": np.sqrt(s((np.exp(base) - ry) ** 2) / n)}


def point_metrics(y: np.ndarray, p: np.ndarray, base: np.ndarray) -> dict[str, float]:
    n = len(y)
    a = metric_arrays(y, p, base, np.arange(n), np.zeros(n, dtype=int), 1)
    return {k: float(a[k][0]) for k in METRICS}


def evaluate(y: np.ndarray, p: np.ndarray, base: np.ndarray, reps: Replicates,
             q: list[float]) -> tuple[dict, dict[str, np.ndarray]]:
    """Point metrics with block-bootstrap CIs, and the replicate values (for paired differences)."""
    boot = metric_arrays(y, p, base, reps.idx, reps.rep, reps.n)
    return {**point_metrics(y, p, base), "ci": {k: ci(boot[k], q) for k in METRICS}}, boot


def _range(v: list[float]) -> dict[str, float]:
    return {"min": float(np.min(v)), "mean": float(np.mean(v)), "max": float(np.max(v))}


# ---------------------------------------------------------------- one variant

@dataclass
class Fit:
    """One learner fitted on one training region for one target: predictions for every site of the variant."""
    pred: np.ndarray
    info: dict
    base: float
    seed_preds: dict[int, np.ndarray] | None


def fits(S: Settings, d: pd.DataFrame, targets: dict[str, np.ndarray], trains: list[Region],
         variant: str) -> tuple[dict[tuple[str, str, str], Fit], list[dict]]:
    """Every (target, training region, learner) fit; training sets smaller than ``min_sites`` are skipped."""
    out, skipped = {}, []
    for target in TARGETS:
        y = targets[target]
        for tr in trains:
            m = tr.mask(d)
            if m.sum() < S.min_sites:
                skipped.append({"variant": variant, "target": target, "train": tr.name, "n_train": int(m.sum()),
                                "reason": f"training set has fewer than phase2.min_test_sites ({S.min_sites}) sites"})
                continue
            for learner in S.learners:
                log.info("us_r2 %s %-13s train %-9s (n=%d) %s", variant, target, tr.name, m.sum(), learner)
                pred, info = fit_predict(S, learner, d[m], y[m], d)
                seeds = ({s: pred if s == S.xgb_seed else fit_predict(S, learner, d[m], y[m], d, seed=s)[0]
                          for s in S.seeds()} if learner == "XGB" else None)
                out[target, tr.name, learner] = Fit(pred, info, float(y[m].mean()), seeds)
    return out, skipped


def score_variant(S: Settings, variant: str, d: pd.DataFrame, targets: dict[str, np.ndarray], trains: list[Region],
                  tests: list[Region]) -> tuple[list[dict], list[dict], list[dict]]:
    """Rows (target x training region x learner x test region), target effects and skipped settings of a variant."""
    B, q = S.bootstrap, S.bootstrap["quantiles"]
    lon, lat = d.lon.to_numpy(float), d.lat.to_numpy(float)
    F, skipped = fits(S, d, targets, trains, variant)
    tr_mask = {r.name: r.mask(d) for r in trains}
    te_mask = {r.name: r.mask(d) for r in tests}
    reps: dict[bytes, Replicates] = {}
    rows, scored = [], {}
    for (target, train, learner), f in F.items():
        y = targets[target]
        for te in tests:
            idx = np.flatnonzero(te_mask[te.name] & ~tr_mask[train])
            if not len(idx):
                skipped.append({"variant": variant, "target": target, "train": train, "test": te.name,
                                "learner": learner, "reason": "no test sites"})
                continue
            key = idx.tobytes()
            if key not in reps:          # rows scored on the same sites share their replicates (paired)
                reps[key] = block_replicates(lon[idx], lat[idx], B["block_deg"], B["n"], B["seed"])
            base = np.full(len(idx), f.base)
            ev, boot = evaluate(y[idx], f.pred[idx], base, reps[key], q)
            row = {"variant": variant, "target": target, "train": train, "test": te.name, "learner": learner,
                   "n_train": int(tr_mask[train].sum()), "n_test": int(len(idx)),
                   "n_test_excluded_as_training_sites": int((te_mask[te.name] & tr_mask[train]).sum()),
                   "below_min_test_sites": bool(len(idx) < S.min_sites), "train_mean_log": f.base, **ev,
                   "fit": f.info}
            if f.seed_preds is not None:
                per_seed = [point_metrics(y[idx], f.seed_preds[s][idx], base) for s in S.seeds()]
                row["seed_spread"] = {"seeds": list(S.seed_spread),
                                      **{k: _range([m[k] for m in per_seed]) for k in SPREAD_METRICS}}
            rows.append(row)
            scored[target, train, learner, te.name] = (row, boot, idx)
    return rows, target_effects(S, variant, F, targets, scored, trains, tests), skipped


def target_effects(S: Settings, variant: str, F: dict[tuple[str, str, str], Fit], targets: dict[str, np.ndarray],
                   scored: dict, trains: list[Region], tests: list[Region]) -> list[dict]:
    """Site-mean minus single-record target, per training region, learner and test region: r2 and rmse_log with a
    paired CI (the same replicates), and for XGB the range over the spread seeds of the r2 difference."""
    q, out = S.bootstrap["quantiles"], []
    for tr in trains:
        for learner in S.learners:
            for te in tests:
                ka, kb = ((t, tr.name, learner, te.name) for t in TARGETS)
                if ka not in scored or kb not in scored:
                    continue
                (a, boot_a, idx), (b, boot_b, idx_b) = scored[ka], scored[kb]
                if not np.array_equal(idx, idx_b):
                    raise RuntimeError("the two targets were scored on different sites")       # cannot happen
                e = {"variant": variant, "train": tr.name, "test": te.name, "learner": learner, "n_test": a["n_test"]}
                for m in EFFECT_METRICS:
                    e[m] = {TARGETS[0]: a[m], TARGETS[1]: b[m], "difference": a[m] - b[m],
                            "ci": ci(boot_a[m] - boot_b[m], q)}
                fa, fb = F[ka[:3]], F[kb[:3]]
                if fa.seed_preds is not None and fb.seed_preds is not None:
                    ya, yb = targets[TARGETS[0]][idx], targets[TARGETS[1]][idx]
                    na, nb = np.full(len(idx), fa.base), np.full(len(idx), fb.base)
                    diffs = [point_metrics(ya, fa.seed_preds[s][idx], na)["r2"]
                             - point_metrics(yb, fb.seed_preds[s][idx], nb)["r2"] for s in S.seeds()]
                    e["seed_spread_r2_difference"] = {"seeds": list(S.seed_spread), **_range(diffs)}
                out.append(e)
    return out


# ---------------------------------------------------------------- figure

def _fmt(v: float) -> str:
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}"


def _tick(te: Region) -> str:
    """Display name of a test region (two lines for a continent outside a box)."""
    return f"{te.continent}\noutside the US box" if te.outside is not None else te.name


def _n_label(rows: list[dict], variants: tuple[str, ...], test: str) -> str:
    parts = []
    for v in variants:
        ns = sorted({r["n_test"] for r in rows if r["variant"] == v and r["test"] == test})
        if ns:
            parts.append(f"{ns[0]}" if len(ns) == 1 else f"{ns[0]}-{ns[-1]}")
    return " / ".join(parts)


def us_r2_figure(cfg: Config, rows: list[dict], S: Settings, trains: list[Region], tests: list[Region]) -> list[Path]:
    """Per learner (rows of panels): R² and RMSE (log Rs) with 95% CIs for each test region (x), per training region
    (colour and marker) and variant (filled: primary; open: the other); site-mean target. A grey dash marks the
    test-set SD of log Rs next to each RMSE (the RMSE of predicting the test-set mean, so R² = 1 - RMSE²/SD²). The R²
    axis stops at ``R2_FLOOR``: a lower R² is drawn on the floor with its value; CIs are cut there."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from ..figures.style import CONTINENT_COLOURS, PALETTE, save_figure
    sel = [r for r in rows if r["target"] == TARGETS[0]]
    get = {(r["variant"], r["train"], r["learner"], r["test"]): r for r in sel}
    learners = [x for x in S.learners if any(r["learner"] == x for r in sel)] or list(S.learners)
    variants = (S.primary,) + tuple(v for v in S.variants if v != S.primary)
    series = [(v, tr.name) for v in variants for tr in trains]
    colour = {trains[0].name: CONTINENT_COLOURS.get(S.train_continent, PALETTE["vermillion"]),
              trains[1].name: PALETTE["black"]}
    marker = {trains[0].name: "o", trains[1].name: "s"}
    offs = (np.arange(len(series)) - (len(series) - 1) / 2) * 0.17
    grid, muted = "#E6E6E6", "#555555"
    fig, axes = plt.subplots(len(learners), 2, figsize=(7.2, 2.2 * len(learners) + 1.3), squeeze=False,
                             sharex=True, sharey="col", constrained_layout=True)
    lows = []
    for li, learner in enumerate(learners):
        a_r2, a_rmse = axes[li]
        for ax in (a_r2, a_rmse):
            ax.set_axisbelow(True)
            ax.grid(axis="y", color=grid, linewidth=0.6)
            ax.tick_params(length=2)
        a_r2.axhline(0.0, color=PALETTE["grey"], linewidth=0.6, zorder=1)
        for si, (v, tr) in enumerate(series):
            kw = dict(marker=marker[tr], color=colour[tr], mec=colour[tr], ms=4.5, linestyle="none",
                      mfc=colour[tr] if v == S.primary else "white", zorder=3)
            for ti, te in enumerate(tests):
                r = get.get((v, tr, learner, te.name))
                if r is None:
                    continue
                x = ti + offs[si]
                lo, hi = r["ci"]["r2"]
                lows.append(lo)
                if r["r2"] < R2_FLOOR:
                    a_r2.plot([x], [R2_FLOOR], clip_on=False, **kw)
                    a_r2.annotate(_fmt(r["r2"]), (x, R2_FLOOR), xytext=(0, 5), textcoords="offset points",
                                  ha="center", va="bottom", fontsize=5.5, color=PALETTE["black"])
                else:
                    a_r2.plot([x, x], [lo, hi], color=colour[tr], linewidth=1.0, zorder=2)
                    a_r2.plot([x], [r["r2"]], **kw)
                lo, hi = r["ci"]["rmse_log"]
                a_rmse.plot([x - 0.055, x + 0.055], [r["sd_log"]] * 2, color=PALETTE["grey"], linewidth=1.4,
                            solid_capstyle="butt", zorder=1)
                a_rmse.plot([x, x], [lo, hi], color=colour[tr], linewidth=1.0, zorder=2)
                a_rmse.plot([x], [r["rmse_log"]], **kw)
        a_r2.set_ylabel("R² (log Rs)")
        a_rmse.set_ylabel("RMSE (log Rs)")
        a_r2.set_title(f"{'abcdefgh'[2 * li]}  {learner}: R²", loc="left")
        a_rmse.set_title(f"{'abcdefgh'[2 * li + 1]}  {learner}: RMSE and test-set SD", loc="left")
        a_rmse.set_ylim(bottom=0.0)
    if lows and min(lows) < R2_FLOOR:
        axes[0][0].set_ylim(bottom=R2_FLOOR - 0.05)
    names = [f"{_tick(te)}\nn = {_n_label(sel, variants, te.name)}" for te in tests]
    for ax in axes[-1]:
        ax.set_xticks(range(len(tests)), names)
        ax.set_xlim(-0.6, len(tests) - 0.4)
    label = {v: ("QC filters" if v == "qc" else "repository filters") for v in variants}
    n_train = {(r["variant"], r["train"]): r["n_train"] for r in sel}
    handles = [Line2D([], [], marker=marker[tr], color=colour[tr], mec=colour[tr], ms=4.5, linestyle="none",
                      mfc=colour[tr] if v == S.primary else "white",
                      label=f"{tr}, {label[v]} ({n_train.get((v, tr), 0)})") for v, tr in series]
    handles.append(Line2D([], [], color=PALETTE["grey"], linewidth=1.4,
                          label="test-set SD of log Rs\n(R² = 1 - RMSE²/SD²)"))
    fig.legend(handles=handles, loc="outside lower center", ncols=len(variants) + 1, frameon=False,
               title="trained on (n sites)", title_fontsize=7, alignment="left")
    B = S.bootstrap
    fig.suptitle(f"Target: site-mean log Rs. Lines: 95% CI ({B['block_deg']:g}° block bootstrap of the test sites). "
                 f"n: test sites, {' / '.join(label[v] for v in variants)}. Exploratory.", fontsize=6.5, color=muted)
    return save_figure(fig, cfg.path("figures", "phase2", "us_r2"))


# ---------------------------------------------------------------- stage

def us_r2(cfg: Config) -> dict:
    S = Settings.from_cfg(cfg)                 # settings are checked before anything is read
    tables = {v: cfg.path("interim", f"features_analysis_{v}.parquet") for v in S.variants}
    rec_path = cfg.path("derived", "records_analysis.parquet")
    require_outputs(cfg, UPSTREAM[0], list(tables.values()))
    require_outputs(cfg, UPSTREAM[1], [rec_path])
    rec = read_table(cfg, rec_path)
    trains, tests = regions(S)
    filters = filter_sets(cfg)
    per_variant, rows, effects, skipped = {}, [], [], []
    for v in S.variants:
        d, info = prepare_sites(read_table(cfg, tables[v]), S)
        sr, sr_info = single_record(rec, d, v, S.target)
        targets = {TARGETS[0]: d[S.target].to_numpy(float), TARGETS[1]: sr[S.target].to_numpy(float)}
        r, e, s = score_variant(S, v, d, targets, trains, tests)
        rows, effects, skipped = rows + r, effects + e, skipped + s
        per_variant[v] = {"primary": v == S.primary, "filters": filters[v], "sites": info,
                          "single_record": sr_info, "regions": composition(d, trains, tests),
                          "overlaps": overlaps(d, trains, tests)}
    figs = us_r2_figure(cfg, rows, S, trains, tests)
    res = {"exploratory": True, "method": method_text(S), "target": S.target, "continent_column": "continent_geo",
           "primary_variant": S.primary, "variants": per_variant,
           "regions": {"train": {r.name: r.describe() for r in trains}, "test": {r.name: r.describe() for r in tests}},
           "targets": {"site_mean": f"the site's mean {S.target} over its records (the v3 target)",
                       "single_record": f"{S.target} of one record per site: a COSORE record first (several: the "
                                        "lowest rec_id), else the lowest SRDB CSV row (the original v1/v2 rule, as "
                                        "E4)"},
           "learner_settings": S.describe(), "bootstrap": S.bootstrap, "min_test_sites": S.min_sites,
           "versions": _versions(), "rows": rows, "target_effect": effects, "skipped": skipped,
           "notes": ["exploratory (brief section 5); North America is used for exploratory analyses only (ground rule "
                     "5); nothing here feeds back into the locked test (ground rule 4)",
                     "r2 = 1 - (rmse_log/sd_log)^2: compare rmse_log and sd_log across test regions before "
                     "comparing r2",
                     "CIs resample test sites only (conditional on the fitted models); test regions are different site "
                     "sets, so differences between them have no paired CI; target_effect is paired",
                     "skill_vs_train_mean rewards fixing the offset between regions (null_bias_log), F-H24",
                     "not the original configuration (F-H29): v3 5-km sites and WorldClim 2.5' instead of the original "
                     "0.05-degree cells and WorldClim 10'; see the module docstring of mshi/analysis/us_r2.py"]}
    write_result(cfg, res, "us_r2.json", outputs=figs, inputs=list(UPSTREAM))
    return {"n_rows": len(rows), "n_target_effects": len(effects), "n_skipped": len(skipped)}
