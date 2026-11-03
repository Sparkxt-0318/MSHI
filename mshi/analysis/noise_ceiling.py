"""Noise ceiling of site-level log Rs: 3-level REML variance components (site / study within site / record) by
continent (Phase 2, brief section 5 item 3; exploratory).

Replaces the handoff's E1 (docs/handoff/scripts/exp_noise_ceiling.py: one-way ANOVA, records treated as independent
replicates, continents pooled for the site-mean ceiling) and the variance decomposition and pair statistic of N3
(exp_reproducibility.py: pairs bootstrapped as if independent). Answers docs/DECISIONS.md F-H19, F-H20 and F-H26.

Data (``phase2.variant``, e.g. qc)
- data/derived/records_analysis.parquet (records with ``site_id_<variant>``) and sites_analysis_<variant>.parquet,
  used only as recorded outputs of a current ``build_sites_analysis`` result (with sites_analysis of every variant).
  Records of sites missing from the site table are left out and counted (a smoke run subsets the site tables, not the
  records). For every site, the record count and the mean log Rs of its records must equal the site table's ``n_rec``
  and ``log_rs`` (the Phase-2 target is that site mean); otherwise the stage refuses to run.
- Continent: the site's geographic continent ``continent_geo`` (D-P2-3), never the locked ``continent`` column. Sites
  whose continent is not in ``phase2.continents`` are left out and counted.
- Study: an SRDB record's study is ``<site_id>_<Study_number>``, nested in its site as in N3 (a Study_number with
  records at several sites becomes one study per site: F-H26; how many do is reported). COSORE records
  (``src == cosore``) have no Study_number; each is its own study, ``cosore_<rec_id>``.

Model, per continent of ``phase2.continents`` and for all of them pooled (one mean: between-continent differences then
count as site variance)
- log_rs_ijk = mu + a_i + b_ij + e_ijk for record k of study j at site i, with a ~ N(0, s2_site), b ~ N(0, s2_study),
  e ~ N(0, s2_record). REML with statsmodels MixedLM: groups = site, a random intercept for site and a variance
  component for study within site. This is N3's model (``vc_formula={"study": "0 + C(study)"}``) built from arrays
  (``VCSpec``): the formula interface calls patsy once per site, so the array form gives the same estimates 3-4 times
  faster (tests/test_noise_ceiling.py checks the two agree). Optimizer: ``noise_ceiling.optimizer``, a list tried in
  order (lbfgs first, as N3): a fit that raises, does not converge or returns a non-finite REML log-likelihood or
  variance is refitted with the next method. statsmodels' lbfgs does all three on some boundary models (e.g. llf =
  +inf with a zero random-intercept variance in South America bootstrap replicates; review C-1, D-P2-17), where bfgs
  and Nelder-Mead reach the REML maximum. Which method produced each fit is recorded.
- Polishing: lbfgs can also report convergence of the interior model short of its maximum, where no fallback is
  triggered (2 of 200 South America replicates, by 0.03 and 0.005 in log-likelihood). So the kept estimate is then
  refined on the closed space directly: the exact REML log-likelihood of this model has a closed form from per-study
  sums (``reml_llf``: compound symmetry within a study, the site intercept by the Woodbury identity; it equals
  statsmodels' REML log-likelihood to about 1e-12, tests/test_noise_ceiling.py), maximised by L-BFGS-B with every
  variance >= 0, started from each usable candidate. The polished components replace the candidate's if their
  log-likelihood is higher by more than ``LLF_TIE``; the gain is recorded (``polish``).
- Fitted on the sites with at least ``noise_ceiling.min_records_per_site`` records.
- The REML maximum over the closed parameter space (variances >= 0). L-BFGS on statsmodels' square-root
  parameterisation can stop short of a zero variance and still report convergence: on the real South America QC records
  it stopped at s2_study = 0.0037, with a REML log-likelihood 0.34 below that of the model without a study variance.
  So both boundary models are fitted as well: s2_study = 0 (``no_study``: random site intercept only) and s2_site = 0
  (``no_site``: random study intercept, groups = study). REML log-likelihoods of these models are comparable (same
  fixed effects); the candidate with the highest one is kept (ties within ``LLF_TIE``: the first in the order interior,
  no_study, no_site). A candidate that raises or does not converge is dropped; with none left the fit has failed.
  ``boundary``: a boundary model was kept, or a kept variance share is below ``ZERO_SHARE``.
- Identification: s2_site is separated from s2_study only by sites with two or more studies, and s2_study from
  s2_record only by studies with two or more records. A fit set with no such site or no such study, or with fewer than
  two sites, is not fitted ("unidentified", "too_few_sites"); the counts are reported (in small continents a handful of
  multi-study sites carry the whole site/study split).

Ceilings (shares of total = s2_site + s2_study + s2_record)
- independent_study = s2_site / total: the R2 of a perfect site-level predictor for one new record from an independent
  study at the site (N3's "reproducibility ceiling");
- same_study = (s2_site + s2_study) / total: the R2 of a perfect predictor of the study mean (the same-study ICC)
  for a new record from a study already observed at the site. It needs a predictor that knows the record's study:
  for predictors constant within a site it is reached only at single-study sites, and is otherwise an upper bound
  that they cannot reach (review C-3). For them the attainable value is ``same_study_site_constant`` =
  (s2_site + s2_study * mean_i sum_j (m_ij / n_i)^2) / total (the new record's study drawn with probability
  m_ij / n_i; the best site-constant predictor is the site effect plus the record-weighted mean of its study effects;
  mean over all sites, singletons included);
- site_mean: for the Phase-2 target, the mean log Rs of all n_i records of site i. Given a_i, that mean has the noise
  variance v_i = s2_study * sum_j (m_ij / n_i)^2 + s2_record / n_i (m_ij records of study j), and
  R2_max = s2_site / (s2_site + mean_i v_i), the mean over ALL sites of the continent, singletons included (their
  v_i = s2_study + s2_record extrapolates components fitted on multi-record sites; checked below).
  ``site_mean_equal_study_weights`` puts s2_study / J_i (J_i studies) in place of the first term (an equal-study-weight
  approximation, not from the brief, which gives no formula): exact only when a site's studies have equal record
  counts, otherwise it understates the noise; reported alongside.
independent_study and site_mean are ceilings for predictors that are constant within a 5-km site (gridded climate
and soil); same_study is one only for a predictor of the study. The within-site variance includes real
plot-to-plot differences (e.g. ecosystem type, F-H19), not only measurement noise.

Checks of that extrapolation (F-H19): the observed variance of the site-mean target over all sites minus the model's
s2_site + mean_i v_i, and the observed variance of the singleton sites' values minus the model's total; both with CIs.

Pair statistic (N3, redone): for every pair of records within a site, half their squared log Rs difference; the mean
over same-study pairs and over different-study pairs (pairs pooled over sites, as N3) and the difference, with the
number of sites contributing pairs and the largest share of pairs from one site (F-H20: a few sites dominate). Every
site with two or more records contributes, whatever ``min_records_per_site``; a COSORE record (its own study) forms
only different-study pairs (N3 used SRDB records only).

Uncertainty: site-cluster bootstrap. In each of ``noise_ceiling.n_boot`` replicates the sites of every continent (all
sites, singletons included) are drawn with replacement, by one generator seeded with ``noise_ceiling.seed``, continent
by continent in config order; a site drawn twice enters as two sites with distinct studies. The pooled replicate is the
union of the continent replicates. Every quantity is recomputed on each replicate (refit as above); percentile
intervals at ``phase2.bootstrap.quantiles`` over the replicates where it is defined. Refits that failed or were
unidentified are counted and left out; refits that ended on the boundary are counted and kept. Replicates run in
``noise_ceiling.n_jobs`` processes (optional, default 1): each is a pure function of its draw, and BLAS runs in one
thread during every fit (threadpoolctl), so the result does not depend on the number of processes or cores. The
processes are spawned, so a script that calls the stage with n_jobs > 1 needs an ``if __name__ == "__main__":`` guard
(``mshi.run`` has one).

Limits
- Nested model only. Effects a Study_number shares across sites count as site variance (F-H26: on the locked data a
  crossed model moved about 4 points of share from site to study); no crossed model is fitted here.
- The CIs condition on the identified, converged refits (counts reported).
- Continents with fewer than ``phase2.min_test_sites`` sites are flagged ``supplementary`` (as in the transfer tables);
  their site/study split rests on very few multi-study sites.
- Exploratory (ground rule 3). Europe and North America are treated like every other continent; nothing here feeds
  back into the locked test (ground rules 4 and 5).
"""
from __future__ import annotations

import logging
import multiprocessing
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels
# imported here, not lazily: statsmodels loads scipy's own BLAS, which threadpool_limits only limits if already loaded
from statsmodels.regression.mixed_linear_model import MixedLM, VCSpec
from threadpoolctl import threadpool_limits

from ..config import Config
from ..io import read_table, require_outputs, write_result

log = logging.getLogger("mshi.noise_ceiling")

UPSTREAM = "build_sites_analysis.json"
RESULT = "noise_ceiling.json"
POOLED = "pooled"
CANDIDATES = ("interior", "no_study", "no_site")
SOURCES = ("srdb", "cosore")
LLF_TIE = 1e-6        # numerical slack: REML log-likelihoods closer than this are tied (first candidate kept)
ZERO_SHARE = 1e-6     # numerical slack: a variance share below this counts as zero (on the boundary)
MEAN_ATOL = 1e-9      # numerical slack: site-table log_rs vs the mean of the site's records
N_EXAMPLES = 10       # how many left-out sites a result lists

METHOD = (
    "3-level REML (statsmodels MixedLM: random site intercept, variance component for study within site) of log Rs "
    "per geographic continent and pooled, on sites with at least min_records_per_site records; REML maximum over the "
    "closed parameter space (interior fit and the two boundary models, highest REML log-likelihood kept). Ceilings: "
    "independent study s2_site/total; same study (s2_site+s2_study)/total; site mean s2_site/(s2_site + mean over all "
    "sites of s2_study*sum_j (m_ij/n_i)^2 + s2_record/n_i). Pair statistic: mean half squared difference of log Rs, "
    "same-study vs different-study record pairs within sites. CIs: site-cluster bootstrap within continents "
    "(duplicated sites relabelled), percentile intervals.")

FORMULAS = {
    "ceiling_independent_study": "s2_site / (s2_site + s2_study + s2_record)",
    "ceiling_same_study": "(s2_site + s2_study) / (s2_site + s2_study + s2_record)",
    "ceiling_same_study_site_constant": "(s2_site + s2_study * mean_i sum_j (m_ij / n_i)^2) / (s2_site + s2_study + "
                                        "s2_record), mean over all sites: a new record from an observed study (study j "
                                        "with probability m_ij / n_i), best predictor constant within the site",
    "ceiling_site_mean": "s2_site / (s2_site + mean_i v_i), v_i = s2_study * sum_j (m_ij / n_i)^2 + s2_record / n_i, "
                         "mean over all sites (singletons included); m_ij records of study j at site i, "
                         "n_i = sum_j m_ij",
    "ceiling_site_mean_equal_study_weights": "s2_site / (s2_site + mean_i (s2_study / J_i + s2_record / n_i)), J_i "
                                             "studies at site i (equal-study-weight approximation; exact for equal "
                                             "m_ij)",
    "pairs": "mean over record pairs within a site of (log_rs_a - log_rs_b)^2 / 2, pairs pooled over sites",
    "check_site_mean_var_diff": "var(site means over all sites) - (s2_site + mean_i v_i)",
    "check_singleton_var_diff": "var(singleton site values) - (s2_site + s2_study + s2_record)",
}

# per-replicate statistics, in output order (fit statistics are NaN when the fit is not "ok")
FIT_STATS = ("s2_site", "s2_study", "s2_record", "total", "share_site", "share_study", "share_record",
             "ceiling_independent_study", "ceiling_same_study", "ceiling_same_study_site_constant", "ceiling_site_mean",
             "ceiling_site_mean_equal_study_weights", "mean_noise_site_mean", "check_site_mean_var_diff",
             "check_singleton_var_diff")
PAIR_STATS = ("pairs_same_study", "pairs_diff_study", "pairs_diff_minus_same")


@dataclass(frozen=True)
class Settings:
    variant: str
    continents: tuple[str, ...]
    min_records: int
    n_boot: int
    seed: int
    quantiles: tuple[float, float]
    optimizer: tuple[str, ...]
    n_jobs: int
    min_test_sites: int

    @classmethod
    def from_cfg(cls, cfg: Config) -> Settings:
        p2 = cfg["phase2"]
        nc = p2["noise_ceiling"]
        missing = [k for k in ("min_records_per_site", "n_boot", "seed", "optimizer") if k not in nc]
        if missing:
            raise KeyError(f"phase2.noise_ceiling in the config lacks {missing} (see mshi/analysis/noise_ceiling.py)")
        opt = nc["optimizer"]
        return cls(variant=p2["variant"], continents=tuple(p2["continents"]),
                   min_records=int(nc["min_records_per_site"]), n_boot=int(nc["n_boot"]), seed=int(nc["seed"]),
                   quantiles=tuple(p2["bootstrap"]["quantiles"]),
                   optimizer=(opt,) if isinstance(opt, str) else tuple(opt), n_jobs=int(nc.get("n_jobs", 1)),
                   min_test_sites=int(p2["min_test_sites"]))


@dataclass(frozen=True)
class Group:
    """The sites of one continent (or of all continents, pooled) and their records, sorted by site, then study, then
    record id; a site's records are rows start[i] .. start[i] + n_rec[i] - 1."""
    name: str
    site_ids: np.ndarray       # (S,) site ids
    start: np.ndarray          # (S,) first record row of each site
    n_rec: np.ndarray          # (S,) records per site (n_i)
    n_study: np.ndarray        # (S,) studies per site (J_i)
    w2: np.ndarray             # (S,) sum_j (m_ij / n_i)^2
    site_mean: np.ndarray      # (S,) the site table's log_rs (= mean of the site's records, checked)
    y: np.ndarray              # (N,) log Rs of the records
    study_local: np.ndarray    # (N,) the record's study index within its site, 0 .. J_i - 1
    pair_same: np.ndarray      # (S, 2) sum of half squared differences and number of same-study pairs
    pair_diff: np.ndarray      # (S, 2) the same for different-study pairs
    srdb_studies_multi_site: int   # SRDB Study_numbers with records at two or more sites of the group


# ---------------------------------------------------------------- data

def _study_number(v: float) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def study_ids(rec: pd.DataFrame, site_col: str) -> pd.Series:
    """Study of each record: ``<site>_<Study_number>`` for SRDB, ``cosore_<rec_id>`` for COSORE (module docstring)."""
    src = rec.src.astype(str)
    if not src.isin(SOURCES).all():
        raise ValueError(f"records with an unknown source: {sorted(set(src) - set(SOURCES))}")
    srdb = src.eq("srdb")
    if (srdb & rec.Study_number.isna()).any():
        raise ValueError(f"{int((srdb & rec.Study_number.isna()).sum())} SRDB records have no Study_number")
    sn = pd.Series("", index=rec.index, dtype=object)
    sn[srdb] = rec.loc[srdb, "Study_number"].map(_study_number)
    return pd.Series(np.where(srdb, rec[site_col].astype(str) + "_" + sn, "cosore_" + rec.rec_id.astype(str)),
                     index=rec.index)


def prepare(rec: pd.DataFrame, sites: pd.DataFrame, s: Settings) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Records of the variant's sites with ``site_id``, ``study`` and ``continent_geo``; the site table restricted to
    the continents of the analysis; counts of what was left out. Refuses (ValueError) inconsistent tables."""
    col = f"site_id_{s.variant}"
    r = rec[rec[col].notna()].copy()
    r["site_id"] = r[col].astype(str)
    st = sites.copy()
    st["site_id"] = st.site_id.astype(str)
    if st.site_id.duplicated().any():
        raise ValueError("the site table has duplicated site ids")
    if not np.isfinite(r.log_rs.to_numpy(float)).all():
        raise ValueError("records with a non-finite log_rs")
    known = r.site_id.isin(st.site_id)
    info = {"records_of_sites_not_in_site_table": int((~known).sum())}
    r = r[known].copy()
    r["study"] = study_ids(r, "site_id")
    agg = r.groupby("site_id").log_rs.agg(["size", "mean"])
    chk = st.set_index("site_id")[["n_rec", "log_rs"]].join(agg, how="left")
    if chk["size"].isna().any():
        raise ValueError(f"{int(chk['size'].isna().sum())} sites of the site table have no record in the records table")
    bad = (chk["size"] != chk.n_rec) | ((chk["mean"] - chk.log_rs).abs() > MEAN_ATOL)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} sites whose record count or mean log Rs differs from the site table "
                         f"(e.g. {sorted(chk.index[bad])[:N_EXAMPLES]})")
    cont = st.continent_geo.where(st.continent_geo.isin(s.continents))
    out = st[cont.isna()]
    info["sites_outside_continents"] = {"n": int(len(out)), "continent_geo": out.continent_geo.astype(str)
                                        .value_counts().sort_index().to_dict(),
                                        "examples": sorted(out.site_id)[:N_EXAMPLES]}
    st = st[cont.notna()]
    r = r[r.site_id.isin(st.site_id)].copy()
    r["continent_geo"] = r.site_id.map(st.set_index("site_id").continent_geo)
    r = r.sort_values(["site_id", "study", "rec_id"], kind="mergesort").reset_index(drop=True)
    return r, st.sort_values("site_id", kind="mergesort").reset_index(drop=True), info


def pair_sums(y: np.ndarray, study_local: np.ndarray, start: np.ndarray,
              n_rec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per site: (sum of half squared differences, number of pairs) over same-study and over different-study pairs."""
    same, diff = np.zeros((len(start), 2)), np.zeros((len(start), 2))
    for i, (a, k) in enumerate(zip(start, n_rec)):
        if k < 2:
            continue
        v, stl = y[a:a + k], study_local[a:a + k]
        iu = np.triu_indices(k, 1)
        h = 0.5 * (v[:, None] - v[None, :])[iu] ** 2
        m = (stl[:, None] == stl[None, :])[iu]
        same[i] = h[m].sum(), m.sum()
        diff[i] = h[~m].sum(), (~m).sum()
    return same, diff


def make_group(name: str, r: pd.DataFrame, st: pd.DataFrame) -> Group:
    """A Group from records sorted by site, study and record id and the site table rows of the same sites."""
    site_ids = st.site_id.to_numpy(str)
    if not len(site_ids):
        e, ef = np.zeros(0, dtype=int), np.zeros(0)
        return Group(name=name, site_ids=site_ids, start=e, n_rec=e, n_study=e, w2=ef, site_mean=ef, y=ef,
                     study_local=e, pair_same=np.zeros((0, 2)), pair_diff=np.zeros((0, 2)), srdb_studies_multi_site=0)
    r = r.set_index("site_id").loc[site_ids].reset_index()          # site order of ``st``, sort within site kept
    n_rec = r.groupby("site_id", sort=False).size().reindex(site_ids).to_numpy(int)
    start = (np.cumsum(n_rec) - n_rec).astype(int)
    first = ~r.duplicated(["site_id", "study"])
    study_local = (first.groupby(r.site_id, sort=False).cumsum() - 1).to_numpy(int)
    m = r.groupby(["site_id", "study"], sort=False).size()
    n_study = m.groupby(level=0, sort=False).size().reindex(site_ids).to_numpy(int)
    w2 = ((m / m.groupby(level=0, sort=False).transform("sum")) ** 2).groupby(level=0, sort=False).sum()
    y = r.log_rs.to_numpy(float)
    same, diff = pair_sums(y, study_local, start, n_rec)
    srdb = r[r.src.astype(str).eq("srdb")]
    multi = int((srdb.groupby("Study_number").site_id.nunique() > 1).sum()) if len(srdb) else 0
    return Group(name=name, site_ids=site_ids, start=start, n_rec=n_rec, n_study=n_study,
                 w2=w2.reindex(site_ids).to_numpy(float), site_mean=st.log_rs.to_numpy(float), y=y,
                 study_local=study_local, pair_same=same, pair_diff=diff, srdb_studies_multi_site=multi)


def build_groups(r: pd.DataFrame, st: pd.DataFrame, continents: tuple[str, ...]) -> dict[str, Group]:
    """One group per continent (config order) and the pooled group (the continents' sites in that order)."""
    groups = {c: make_group(c, r[r.continent_geo == c], st[st.continent_geo == c]) for c in continents}
    order = pd.concat([st[st.continent_geo == c] for c in continents], ignore_index=True)
    groups[POOLED] = make_group(POOLED, r, order)
    return groups


def replicate(g: Group, draw: np.ndarray, min_records: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(y, site, study) of the drawn sites with at least ``min_records`` records, as integer codes in row order. Every
    draw position is its own site and its studies are new studies, so a site drawn twice enters as two sites."""
    keep = draw[g.n_rec[draw] >= min_records]
    n = g.n_rec[keep]
    rows = (np.concatenate([np.arange(a, a + k) for a, k in zip(g.start[keep], n)]) if len(keep)
            else np.zeros(0, dtype=int))
    site = np.repeat(np.arange(len(keep)), n)
    offset = np.cumsum(g.n_study[keep]) - g.n_study[keep]
    study = np.repeat(offset, n) + g.study_local[rows]
    return g.y[rows], site, study


# ---------------------------------------------------------------- model

def identification(site: np.ndarray, study: np.ndarray) -> dict:
    """Counts that decide whether the three variances are separable (module docstring)."""
    n_sites = int(site[-1] + 1) if len(site) else 0
    n_studies = int(study[-1] + 1) if len(study) else 0
    first = np.r_[True, study[1:] != study[:-1]] if len(study) else np.zeros(0, dtype=bool)
    per_site = np.bincount(site[first], minlength=n_sites)
    per_study = np.bincount(study, minlength=n_studies)
    return {"sites": n_sites, "studies": n_studies, "records": int(len(site)),
            "sites_2plus_studies": int((per_site >= 2).sum()), "studies_2plus_records": int((per_study >= 2).sum())}


def _vcspec(site: np.ndarray, study: np.ndarray):
    """``VCSpec`` of the study-within-site variance component: per site (sorted group order), the record-by-study
    indicator matrix; the model of ``vc_formula={"study": "0 + C(study)"}``."""
    cut = np.flatnonzero(np.r_[True, site[1:] != site[:-1], True])
    names, mats = [], []
    for a, b in zip(cut[:-1], cut[1:]):
        local = study[a:b] - study[a]
        m = np.zeros((b - a, int(local[-1]) + 1))
        m[np.arange(b - a), local] = 1.0
        names.append([str(k) for k in range(m.shape[1])])
        mats.append(m)
    return VCSpec(["study"], [names], [mats])


def _fit_candidate(kind: str, y: np.ndarray, site: np.ndarray, study: np.ndarray, optimizer) -> dict:
    """One REML fit: the interior model or a boundary model (module docstring), with the methods of ``optimizer``
    tried in order until a fit is usable (converged, finite log-likelihood and variances, no error)."""
    methods = (optimizer,) if isinstance(optimizer, str) else tuple(optimizer)
    failed = []
    for method in methods:
        out = _fit_once(kind, y, site, study, method)
        if out["usable"]:
            break
        failed.append({"method": method, "converged": out["converged"], "llf": out["llf"], "error": out["error"]})
    out["method"] = method if out["usable"] else None
    out["failed_methods"] = failed
    return out


def _fit_once(kind: str, y: np.ndarray, site: np.ndarray, study: np.ndarray, method: str) -> dict:
    one = np.ones((len(y), 1))
    out: dict = {"usable": False, "converged": None, "llf": None, "error": None}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            if kind == "interior":
                model = MixedLM(y, one, groups=site, exog_re=one, exog_vc=_vcspec(site, study))
            elif kind == "no_study":
                model = MixedLM(y, one, groups=site, exog_re=one)
            else:
                model = MixedLM(y, one, groups=study, exog_re=one)
            f = model.fit(reml=True, method=method)
            re = float(np.asarray(f.cov_re)[0, 0])
            vc = float(np.asarray(f.vcomp)[0]) if kind == "interior" else 0.0
            s2 = {"interior": (re, vc), "no_study": (re, 0.0), "no_site": (0.0, re)}[kind]
            out.update(converged=bool(f.converged), llf=float(f.llf),        # llf is computed here, lazily
                       s2_site=s2[0], s2_study=s2[1], s2_record=float(f.scale))
            out["usable"] = bool(f.converged and np.isfinite([out["llf"], *s2, out["s2_record"]]).all())
        except (np.linalg.LinAlgError, ValueError, ZeroDivisionError, FloatingPointError) as e:
            out["error"] = f"{type(e).__name__}: {e}"
    out["warnings"] = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
    return out


def study_sums(y: np.ndarray, site: np.ndarray, study: np.ndarray) -> tuple:
    """Per study (records in site and study order): its site index (0 .. sites - 1), record count, sum and sum of
    squares of y; plus the numbers of sites and records."""
    starts = np.flatnonzero(np.r_[True, (site[1:] != site[:-1]) | (study[1:] != study[:-1])])
    m = np.diff(np.r_[starts, len(y)]).astype(float)
    _, st_site = np.unique(site[starts], return_inverse=True)
    return st_site, m, np.add.reduceat(y, starts), np.add.reduceat(y * y, starts), int(st_site.max()) + 1, len(y)


def reml_llf(s2, sums: tuple) -> float:
    """Exact REML log-likelihood of log_rs = mu + a_i + b_ij + e_ijk at s2 = (s2_site, s2_study, s2_record), from
    ``study_sums`` (statsmodels' convention, including the constant)."""
    sa, sb, se = (float(v) for v in s2)
    st_site, m, S, Q, n_sites, N = sums
    a = 1.0 / (se + m * sb)                          # 1'B_j^-1 1 = m_j a_j for the study block B_j
    c = np.bincount(st_site, m * a, n_sites)         # per site: 1'B^-1 1
    u = np.bincount(st_site, a * S, n_sites)         # 1'B^-1 y
    w = np.bincount(st_site, (Q - sb * a * S * S) / se, n_sites)    # y'B^-1 y
    den = 1.0 + sa * c                               # V_i = B + s2_site 11' (Woodbury)
    logdet = float(np.sum((m - 1) * np.log(se) + np.log(se + m * sb)) + np.sum(np.log(den)))
    A, b1, yy = float(np.sum(c / den)), float(np.sum(u / den)), float(np.sum(w - sa * u * u / den))
    mu = b1 / A
    return -0.5 * ((N - 1) * np.log(2 * np.pi) + logdet + np.log(A) + yy - 2 * mu * b1 + mu * mu * A)


def polish(sums: tuple, starts: list[tuple[float, float, float]], var_y: float) -> tuple[np.ndarray, float]:
    """The REML maximum over the closed parameter space found by L-BFGS-B from each start (module docstring)."""
    from scipy.optimize import minimize
    lo = 1e-9 * var_y if var_y > 0 else 1e-12        # s2_record must stay positive
    best_x, best_f = None, -np.inf
    for x0 in starts:
        x0 = np.maximum(np.asarray(x0, float), [0.0, 0.0, lo])
        r = minimize(lambda x: -reml_llf(x, sums), x0, method="L-BFGS-B",
                     bounds=[(0.0, None), (0.0, None), (lo, None)], options={"ftol": 1e-15, "gtol": 1e-10,
                                                                             "maxiter": 2000})
        f = -float(r.fun)
        if np.isfinite(f) and f > best_f:
            best_x, best_f = np.asarray(r.x, float), f
    return best_x, best_f


def choose(cands: dict[str, dict]) -> str | None:
    """The usable candidate with the highest REML log-likelihood (ties within LLF_TIE: the first in CANDIDATES)."""
    ok = [k for k in CANDIDATES if cands.get(k, {}).get("usable")]
    if not ok:
        return None
    best = max(cands[k]["llf"] for k in ok)
    return next(k for k in ok if cands[k]["llf"] >= best - LLF_TIE)


def fit_nested(y: np.ndarray, site: np.ndarray, study: np.ndarray, optimizer) -> dict:
    """REML fit of the nested model on records in site and study order (integer codes). ``status``: ok, failed,
    unidentified or too_few_sites; for ok, the kept candidate, its components and ``boundary``."""
    ident = identification(site, study)
    out: dict = {"n": ident, "candidates": {}}
    if ident["sites"] < 2:
        return {**out, "status": "too_few_sites"}
    if ident["sites_2plus_studies"] < 1 or ident["studies_2plus_records"] < 1:
        return {**out, "status": "unidentified"}
    cands = {k: _fit_candidate(k, y, site, study, optimizer) for k in CANDIDATES}
    out["candidates"] = cands
    k = choose(cands)
    if k is None:
        return {**out, "status": "failed"}
    c = cands[k]
    s2 = np.array([c["s2_site"], c["s2_study"], c["s2_record"]])
    sums = study_sums(y, site, study)
    llf0 = reml_llf(s2, sums)
    starts = [(v["s2_site"], v["s2_study"], v["s2_record"]) for v in cands.values() if v["usable"]]
    x, llf1 = polish(sums, starts, float(np.var(y)))
    applied = x is not None and llf1 > llf0 + LLF_TIE
    if applied:
        s2 = x
    out["polish"] = {"applied": bool(applied), "llf_gain": float(llf1 - llf0) if x is not None else None,
                     "llf": float(max(llf0, llf1) if x is not None else llf0)}
    total = float(s2.sum())
    boundary = k != "interior" or min(s2[0], s2[1]) < ZERO_SHARE * total
    return {**out, "status": "ok", "chosen": k, "boundary": bool(boundary),
            "s2_site": float(s2[0]), "s2_study": float(s2[1]), "s2_record": float(s2[2])}


def ceilings(s2_site: float, s2_study: float, s2_record: float, n_rec: np.ndarray, n_study: np.ndarray,
             w2: np.ndarray) -> dict:
    """Variance shares and the three ceilings (module docstring) for sites with n_rec records in n_study studies and
    squared study weights w2 = sum_j (m_ij / n_i)^2."""
    total = s2_site + s2_study + s2_record
    noise = s2_study * w2 + s2_record / n_rec
    noise_eq = s2_study / n_study + s2_record / n_rec
    return {"total": total, "share_site": s2_site / total, "share_study": s2_study / total,
            "share_record": s2_record / total, "ceiling_independent_study": s2_site / total,
            "ceiling_same_study": (s2_site + s2_study) / total,
            "ceiling_same_study_site_constant": (s2_site + s2_study * float(w2.mean())) / total,
            "ceiling_site_mean": s2_site / (s2_site + noise.mean()),
            "ceiling_site_mean_equal_study_weights": s2_site / (s2_site + noise_eq.mean()),
            "mean_noise_site_mean": float(noise.mean())}


def pair_stats(g: Group, mult: np.ndarray) -> dict:
    """Pair-weighted mean half squared differences of same- and different-study pairs, each site's pairs counted
    ``mult`` times (its number of draws)."""
    out = {}
    for name, arr in (("pairs_same_study", g.pair_same), ("pairs_diff_study", g.pair_diff)):
        n = float(np.sum(mult * arr[:, 1]))
        out[name] = float(np.sum(mult * arr[:, 0]) / n) if n > 0 else np.nan
    out["pairs_diff_minus_same"] = out["pairs_diff_study"] - out["pairs_same_study"]
    return out


def replicate_stats(g: Group, draw: np.ndarray, min_records: int, optimizer) -> dict:
    """Every statistic of FIT_STATS and PAIR_STATS for the sites ``draw`` (indices into the group's sites; the identity
    for the point estimate), plus the fit itself under ``fit``."""
    y, site, study = replicate(g, draw, min_records)
    fit = fit_nested(y, site, study, optimizer)
    st = dict.fromkeys(FIT_STATS, np.nan)
    if fit["status"] == "ok":
        n_rec, n_study, w2 = g.n_rec[draw], g.n_study[draw], g.w2[draw]
        st.update(s2_site=fit["s2_site"], s2_study=fit["s2_study"], s2_record=fit["s2_record"])
        st.update(ceilings(fit["s2_site"], fit["s2_study"], fit["s2_record"], n_rec, n_study, w2))
        means = g.site_mean[draw]
        if len(means) >= 2:
            implied = fit["s2_site"] + st["mean_noise_site_mean"]
            st["check_site_mean_var_diff"] = float(np.var(means, ddof=1) - implied)
        single = means[n_rec == 1]
        if len(single) >= 2:
            st["check_singleton_var_diff"] = float(np.var(single, ddof=1) - st["total"])
    st.update(pair_stats(g, np.bincount(draw, minlength=len(g.site_ids))))
    return {"stats": st, "fit": fit}


# ---------------------------------------------------------------- bootstrap

def draws(groups: dict[str, Group], s: Settings) -> list[dict[str, np.ndarray]]:
    """Site draws of every replicate: per continent (config order) with replacement from one generator; the pooled
    draw is the union, as indices into the pooled group's sites (the continents' sites in config order)."""
    rng = np.random.default_rng(s.seed)
    sizes = [len(groups[c].site_ids) for c in s.continents]
    offsets = np.r_[0, np.cumsum(sizes)[:-1]]
    out = []
    for _ in range(s.n_boot):
        d = {c: (rng.integers(0, n, n) if n else np.zeros(0, dtype=int)) for c, n in zip(s.continents, sizes)}
        d[POOLED] = np.concatenate([o + d[c] for c, o in zip(s.continents, offsets)]).astype(int)
        out.append(d)
    return out


_WORKER: dict = {}


def _init_worker(groups: dict[str, Group], min_records: int, optimizer, one_blas_thread: bool = False) -> None:
    _WORKER.update(groups=groups, min_records=min_records, optimizer=optimizer)
    if one_blas_thread:              # a worker process: one BLAS thread for its lifetime (see ``noise_ceiling``)
        _WORKER["blas_limit"] = threadpool_limits(limits=1)


def _boot_task(task: tuple[str, np.ndarray]) -> dict:
    name, draw = task
    res = replicate_stats(_WORKER["groups"][name], draw, _WORKER["min_records"], _WORKER["optimizer"])
    fit = res["fit"]
    cands = fit.get("candidates") or {}
    return {"stats": res["stats"], "status": fit["status"], "chosen": fit.get("chosen"),
            "boundary": bool(fit.get("boundary", False)),
            "dropped": [k for k in CANDIDATES if k in cands and not cands[k]["usable"]],
            "fallback": [k for k in CANDIDATES if k in cands and cands[k]["usable"] and cands[k]["failed_methods"]],
            "polished": bool((fit.get("polish") or {}).get("applied", False))}


def run_bootstrap(groups: dict[str, Group], s: Settings) -> dict[str, list[dict]]:
    """Per group, the outcome of every replicate (in replicate order; the same for any ``n_jobs``)."""
    names = list(s.continents) + [POOLED]
    tasks = [(name, d[name]) for d in draws(groups, s) for name in names]
    if s.n_jobs > 1 and tasks:
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=s.n_jobs, mp_context=ctx, initializer=_init_worker,
                                 initargs=(groups, s.min_records, s.optimizer, True)) as ex:
            res = list(ex.map(_boot_task, tasks, chunksize=max(1, len(tasks) // (8 * s.n_jobs))))
    else:
        _init_worker(groups, s.min_records, s.optimizer)
        res = [_boot_task(t) for t in tasks]
    out: dict[str, list[dict]] = {name: [] for name in names}
    for (name, _d), r in zip(tasks, res):
        out[name].append(r)
    return out


def _ci(values: np.ndarray, q: tuple[float, float]) -> tuple[list[float] | None, int]:
    v = values[np.isfinite(values)]
    if not len(v):
        return None, 0
    return [float(np.quantile(v, q[0])), float(np.quantile(v, q[1]))], int(len(v))


def summarise_boot(reps: list[dict], q: tuple[float, float]) -> tuple[dict, dict]:
    """(per statistic: CI and number of replicates used; counts of replicate outcomes)."""
    ci = {}
    for k in FIT_STATS + PAIR_STATS:
        c, n = _ci(np.array([r["stats"][k] for r in reps], dtype=float), q)
        ci[k] = {"ci": c, "n_boot_used": n}
    status = [r["status"] for r in reps]
    counts = {"n": len(reps), **{k: status.count(k) for k in ("ok", "failed", "unidentified", "too_few_sites")},
              "boundary": int(sum(r["boundary"] for r in reps if r["status"] == "ok")),
              "kept_candidate": {k: sum(r["chosen"] == k for r in reps) for k in CANDIDATES},
              "dropped_candidate": {k: sum(k in r["dropped"] for r in reps) for k in CANDIDATES},
              "candidate_fit_by_fallback_method": {k: sum(k in r["fallback"] for r in reps) for k in CANDIDATES},
              "polished": int(sum(r["polished"] for r in reps if r["status"] == "ok"))}
    return ci, counts


# ---------------------------------------------------------------- results

def _pairs_detail(g: Group) -> dict:
    out = {}
    for name, arr in (("same_study", g.pair_same), ("diff_study", g.pair_diff)):
        n = arr[:, 1]
        out[name] = {"n_pairs": int(n.sum()), "n_sites": int((n > 0).sum()),
                     "max_site_share": float(n.max() / n.sum()) if n.sum() > 0 else None}
    return out


def group_result(g: Group, point: dict, ci: dict, counts: dict, s: Settings) -> dict:
    fit, st = point["fit"], point["stats"]

    def est(k: str) -> dict:
        return {"estimate": st[k], **ci[k]}

    cands = {k: {kk: v.get(kk) for kk in ("usable", "method", "failed_methods", "converged", "llf", "error",
                                          "warnings", "s2_site", "s2_study", "s2_record")}
             for k, v in (fit.get("candidates") or {}).items()}
    single = g.n_rec == 1
    return {
        "supplementary": bool(len(g.site_ids) < s.min_test_sites),
        "n": {"sites": int(len(g.site_ids)), "singleton_sites": int(single.sum()), "records": int(g.n_rec.sum()),
              "sites_fit": fit["n"]["sites"], "studies_fit": fit["n"]["studies"], "records_fit": fit["n"]["records"],
              "sites_fit_2plus_studies": fit["n"]["sites_2plus_studies"],
              "studies_fit_2plus_records": fit["n"]["studies_2plus_records"],
              "srdb_studies_at_2plus_sites": g.srdb_studies_multi_site},
        "fit": {"status": fit["status"], "kept": fit.get("chosen"), "boundary": fit.get("boundary"),
                "polish": fit.get("polish"), "candidates": cands},
        "components": {k: est(k) for k in ("s2_site", "s2_study", "s2_record", "total")},
        "shares": {k.removeprefix("share_"): est(k) for k in ("share_site", "share_study", "share_record")},
        "ceilings": {k.removeprefix("ceiling_"): est(k) for k in ("ceiling_independent_study", "ceiling_same_study",
                                                                   "ceiling_same_study_site_constant",
                                                                   "ceiling_site_mean",
                                                                   "ceiling_site_mean_equal_study_weights")},
        "mean_noise_site_mean": est("mean_noise_site_mean"),
        "checks": {"site_mean_var_diff": est("check_site_mean_var_diff"),
                   "singleton_var_diff": est("check_singleton_var_diff"),
                   "observed_var_site_mean": float(np.var(g.site_mean, ddof=1)) if len(g.site_mean) >= 2 else None,
                   "observed_var_singletons": (float(np.var(g.site_mean[single], ddof=1)) if single.sum() >= 2
                                               else None)},
        "pairs": {**{k: {**v, "semivariance": est(f"pairs_{k}")} for k, v in _pairs_detail(g).items()},
                  "diff_minus_same": est("pairs_diff_minus_same")},
        "bootstrap": counts,
    }


def noise_ceiling(cfg: Config) -> dict:
    """The stage (module docstring): writes results/noise_ceiling.json and figures/phase2/noise_ceiling.{png,pdf};
    returns the three ceilings per group for the run log."""
    s = Settings.from_cfg(cfg)
    if s.variant not in cfg["site_build"]["variants"]:
        raise ValueError(f"phase2.variant {s.variant!r} is not a site-build variant {cfg['site_build']['variants']}")
    rec_path = cfg.path("derived", "records_analysis.parquet")
    site_paths = {t: cfg.path("derived", f"sites_analysis_{t}.parquet") for t in cfg["site_build"]["variants"]}
    require_outputs(cfg, UPSTREAM, [rec_path, *site_paths.values()])
    r, st, info = prepare(read_table(cfg, rec_path), read_table(cfg, site_paths[s.variant]), s)
    groups = build_groups(r, st, s.continents)
    with threadpool_limits(limits=1):       # BLAS in one thread: no result depends on the core count or n_jobs
        t0 = time.perf_counter()
        points = {name: replicate_stats(g, np.arange(len(g.site_ids)), s.min_records, s.optimizer)
                  for name, g in groups.items()}
        t1 = time.perf_counter()
        boot = run_bootstrap(groups, s)
        t2 = time.perf_counter()
    n_fits = sum(len(p["fit"]["candidates"]) for p in points.values())
    n_boot_fits = sum(len(CANDIDATES) for reps in boot.values() for x in reps if x["status"] in ("ok", "failed"))
    log.info("noise_ceiling: %d point fits in %.1f s; %d bootstrap fits in %.1f s (%.2f fits/s, n_jobs %d)", n_fits,
             t1 - t0, n_boot_fits, t2 - t1, n_boot_fits / max(t2 - t1, 1e-9), s.n_jobs)
    res_groups = {}
    for name, g in groups.items():
        ci, counts = summarise_boot(boot[name], s.quantiles)
        res_groups[name] = group_result(g, points[name], ci, counts, s)
    res = {"exploratory": True, "method": METHOD, "formulas": FORMULAS, "variant": s.variant,
           "settings": {"continents": list(s.continents), "min_records_per_site": s.min_records, "n_boot": s.n_boot,
                        "seed": s.seed, "quantiles": list(s.quantiles), "optimizer": list(s.optimizer),
                        "llf_tie": LLF_TIE, "zero_share": ZERO_SHARE, "continent_column": "continent_geo"},
           "data": {"records": int(len(r)), "sites": int(len(st)),
                    "cosore_records": int(r.src.astype(str).eq("cosore").sum()), **info},
           "groups": res_groups, "fits": {"point": n_fits, "bootstrap": n_boot_fits},
           "versions": {"statsmodels": statsmodels.__version__, "numpy": np.__version__}}
    figs = figure(cfg, res, s)
    write_result(cfg, res, RESULT, outputs=figs, inputs=[UPSTREAM])

    def num(x: float) -> float | None:          # the run log is plain JSON: no NaN
        return float(x) if np.isfinite(x) else None

    keys = ("independent_study", "same_study", "site_mean")
    return {"exploratory": True, "variant": s.variant,
            "groups": {k: {"status": v["fit"]["status"], **{c: num(v["ceilings"][c]["estimate"]) for c in keys}}
                       for k, v in res_groups.items()}}


# ---------------------------------------------------------------- figure

def figure(cfg: Config, res: dict, s: Settings) -> list[Path]:
    """Three panels per group (continents in config order, then pooled): variance shares; the three ceilings with
    CIs; same- vs different-study pair semivariances with CIs."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    from ..figures.style import PALETTE, save_figure
    names = list(s.continents) + [POOLED]
    G = res["groups"]
    rows = np.arange(len(names))[::-1].astype(float)
    labels = [("All continents" if k == POOLED else k) + ("*" if G[k]["supplementary"] else "") for k in names]
    grid, muted = "#E6E6E6", "#555555"
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 0.34 * len(names) + 1.7), sharey=True, gridspec_kw={"wspace": 0.12})
    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(axis="x", color=grid, linewidth=0.6)
        ax.tick_params(length=2)
        ax.axhline(rows[-1] + 0.5, color=grid, linewidth=0.6)        # separates the pooled row
    parts = [("site", "Site", PALETTE["blue"]), ("study", "Study within site", PALETTE["orange"]),
             ("record", "Record", PALETTE["green"])]
    for y, k in zip(rows, names):
        left = 0.0
        for part, _label, colour in parts:
            v = G[k]["shares"][part]["estimate"]
            if v is not None and np.isfinite(v):
                axes[0].barh(y, v, left=left, height=0.5, color=colour, edgecolor="white", linewidth=0.8)
                left += v
    axes[0].set_xlim(0, 1)
    axes[0].set_yticks(rows, [f"{lab} ({G[k]['n']['sites_fit']}/{G[k]['n']['sites']})"
                              for lab, k in zip(labels, names)])
    axes[0].set_xlabel("Share of log Rs variance (REML)")
    axes[0].set_title("a  Variance shares", loc="left")
    series_b = [("independent_study", "New record, independent study", PALETTE["blue"], "o", 0.2),
                ("same_study", "New record, same study (a predictor of the study)", PALETTE["orange"], "s", 0.0),
                ("site_mean", "Site mean (the Phase-2 target)", PALETTE["black"], "D", -0.2)]
    _dots(axes[1], rows, [[G[k]["ceilings"][key] for k in names] for key, *_ in series_b], series_b)
    axes[1].set_xlim(0, 1)
    axes[1].set_xlabel("Ceiling R² (95% CI)")
    axes[1].set_title("b  Noise ceilings", loc="left")
    series_c = [("same_study", "Same-study pairs", PALETTE["green"], "o", 0.12),
                ("diff_study", "Different-study pairs", PALETTE["orange"], "s", -0.12)]
    _dots(axes[2], rows, [[G[k]["pairs"][key]["semivariance"] for k in names] for key, *_ in series_c], series_c)
    axes[2].set_xlim(left=0)
    axes[2].set_xlabel("Semivariance of log Rs (95% CI)")
    axes[2].set_title("c  Record pairs in a site", loc="left")
    handles = [[Patch(facecolor=c, label=lab) for _p, lab, c in parts]]
    handles += [[Line2D([], [], color=c, marker=m, markeredgecolor="white", markeredgewidth=0.6, label=lab)
                 for _k, lab, c, m, _dy in ser] for ser in (series_b, series_c)]
    legends = [ax.legend(handles=h, loc="upper left", bbox_to_anchor=(0.0, -0.2), frameon=False, handlelength=1.4)
               for ax, h in zip(axes, handles)]
    fig.canvas.draw()                                   # the note goes below the lowest legend
    low = min(leg.get_window_extent(fig.canvas.get_renderer()).y0 for leg in legends)
    y = fig.transFigure.inverted().transform((0.0, low))[1]
    fig.text(0.0, y - 0.01, f"(n/N): sites fitted / all sites. * fewer than {s.min_test_sites} sites. CIs: "
             f"site-cluster bootstrap, {s.n_boot} replicates. Exploratory.", fontsize=6, color=muted, va="top")
    return save_figure(fig, cfg.path("figures", "phase2", "noise_ceiling"))


def _dots(ax, rows: np.ndarray, values: list[list[dict]], series) -> None:
    """Point estimates with CI whiskers; one vertical offset per series."""
    for vals, (_key, _label, colour, marker, dy) in zip(values, series):
        for y, v in zip(rows, vals):
            e = v["estimate"]
            if e is None or not np.isfinite(e):
                continue
            if v["ci"] is not None:
                ax.plot(v["ci"], [y + dy] * 2, color=colour, linewidth=1.0, solid_capstyle="round")
            ax.plot([e], [y + dy], marker=marker, color=colour, markersize=4.5, markeredgecolor="white",
                    markeredgewidth=0.6, linestyle="none")
