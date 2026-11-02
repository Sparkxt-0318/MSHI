"""The locked Asia -> Europe clean test (docs/handoff/ANALYSIS_PLAN_LOCKED.md).

Port of ``docs/handoff/scripts/clean_test.py``. The test was scored once on 2026-11-01; its result
(docs/handoff/results/clean_test_europe.json) is final and is never overwritten. Running this stage
again is a reproducibility check only: outputs go to results/clean_test_rerun_<variant>.json, with a
``vs_locked`` deviation block, and are compared with the handoff numbers by ``repro_checks``.

What the lock covers (``verify_lock``; the stage refuses to run, and writes nothing, unless all hold):
1. SHA-256 of the plan file == ``PLAN_SHA256`` anchored in this module == ``clean_test.plan_sha256`` in
   the config == the hash recorded next to the plan (ANALYSIS_PLAN_LOCKED.sha256);
2. SHA-256 of the canonical JSON of ``clean_test.locked`` (continents, target, predictor sets, learners
   and parameters, OLS-TP form, CV design and seeds, tie margin, bootstrap settings and CI quantiles, seed
   spread, AOA settings) == ``LOCKED_SHA256`` anchored here == ``clean_test.locked_sha256``; editing the
   config, or passing another ``--config``, therefore cannot change the definition;
3. the locked result files have the SHA-256s anchored in ``LOCKED_RESULT_SHA256`` (the reference for the
   deviation report cannot change silently), and ``clean_test.variants`` re-runs every one of them (the
   plan-specified repo-filter sensitivity cannot be dropped from the re-run).
The algorithm (selection loop and tie rule, scoring, metrics, AOA) is the code below; it is pinned by
tests/test_guards.py::test_locked_code_unchanged (hash of its syntax tree). Changing it or any anchor is
a deviation from the locked plan and must be logged in docs/DECISIONS.md (ground rule 4).

Deviation from the prototype (docs/DECISIONS.md DEV-P1-15): random-forest predictions are computed with
``rf.predict_n_jobs`` = 1. The fitted forests are identical; summing the trees in a fixed order makes the
result bit-reproducible (with n_jobs = 2 the sum order follows thread completion; differences ~1e-16).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from ..config import Config, canonical_sha256
from ..io import read_json, read_table, require_outputs, sha256_file, write_result
from ..spatial import block_folds, bootstrap_ci

log = logging.getLogger("mshi.clean_test")

# Anchors (see module docstring). Kept in code as well as in configs/v3.yaml on purpose.
PLAN_SHA256 = "9d50e120c42fa8b4ffdac7b98be1cfa461d4c22b7eac7f9a4aaf01e0befe3dac"
LOCKED_SHA256 = "ef029090d17d2a428cff48a710753cee75b63cf2f00748a73f1114798a4dae7f"
LOCKED_RESULT_SHA256 = {
    "qc": "b091795f9127d1de873ce42290b391d3d006775c9404ff36f0cb79671256d1e6",     # clean_test_europe.json
    "repo": "48aa5bebf01c855d70a66623396b496fa875e8775402075486fa514c3539f9db",   # ..._repo_sensitivity.json
}


class LockedPlanError(RuntimeError):
    """The locked plan, the locked test definition or a locked result does not match its anchored hash."""


def verify_lock(cfg: Config) -> dict:
    """Refuse (LockedPlanError) unless plan, definition and locked results match the anchored hashes.
    Messages name the expected hash only (never a replacement value)."""
    ct = cfg["clean_test"]
    if ct.get("plan_sha256") != PLAN_SHA256:
        raise LockedPlanError("clean_test.plan_sha256 in the config differs from the plan hash anchored in "
                              f"mshi/analysis/clean_test.py ({PLAN_SHA256}). Refusing to run.")
    plan = cfg.repo_path(ct["plan"])
    if not plan.exists():
        raise LockedPlanError(f"locked plan not found: {plan}")
    if sha256_file(plan) != PLAN_SHA256:
        raise LockedPlanError(f"{plan}: content does not match the locked SHA-256 {PLAN_SHA256}; the plan has "
                              "been modified. Refusing to run.")
    side = plan.with_suffix(".sha256")
    if not side.exists() or side.read_text().split()[0] != PLAN_SHA256:
        raise LockedPlanError(f"{side}: missing, or does not record the locked hash {PLAN_SHA256}. Refusing to run.")
    if ct.get("locked_sha256") != LOCKED_SHA256 or canonical_sha256(ct["locked"]) != LOCKED_SHA256:
        raise LockedPlanError("clean_test.locked in the config (or its recorded hash) differs from the locked test "
                              f"definition anchored in mshi/analysis/clean_test.py ({LOCKED_SHA256}). The locked "
                              "test definition must not change. Refusing to run.")
    lr = ct.get("locked_results", {})
    for tag, digest in LOCKED_RESULT_SHA256.items():
        f = lr.get(tag, {})
        p = cfg.repo_path(f.get("file", ""))
        if f.get("sha256") != digest or not p.is_file() or sha256_file(p) != digest:
            raise LockedPlanError(f"locked result for '{tag}' ({f.get('file')}) is missing or does not match the "
                                  f"anchored SHA-256 {digest}. Refusing to run.")
    if sorted(ct.get("variants", [])) != sorted(LOCKED_RESULT_SHA256):
        raise LockedPlanError(f"clean_test.variants must re-run every locked variant {sorted(LOCKED_RESULT_SHA256)}, "
                              f"got {ct.get('variants')}. Refusing to run.")
    return {"plan": str(plan.relative_to(cfg.repo_root)), "plan_sha256": PLAN_SHA256,
            "locked_sha256": LOCKED_SHA256, "locked_results_sha256": dict(LOCKED_RESULT_SHA256)}


class LockedTest:
    """The locked analysis. ``require_lock=False`` is for tests that run the machinery with lighter,
    explicitly modified settings on synthetic data; the ``clean_test`` stage always verifies the lock."""

    def __init__(self, cfg: Config, *, require_lock: bool = True):
        self.lock = verify_lock(cfg) if require_lock else None
        self.L = cfg["clean_test"]["locked"]
        self.T = self.L["target"]
        self.sets = self.L["sets"]
        self.cands = [(s, l) for s in self.sets for l in self.L["ml_learners"]] + [("TP", "OLS-TP")]

    def make(self, learner: str, seed: int | None = None):
        seed = self.L["model_seed"] if seed is None else seed
        if learner == "XGB":
            import xgboost as xgb
            return xgb.XGBRegressor(**self.L["xgb"], random_state=seed)
        if learner == "RF":
            rf = self.L["rf"]
            return RandomForestRegressor(rf["n_estimators"], min_samples_leaf=rf["min_samples_leaf"],
                                         max_features=rf["max_features"], random_state=seed, n_jobs=rf["n_jobs"])
        return LinearRegression()

    def fit(self, learner: str, X: np.ndarray, y: np.ndarray, seed: int | None = None):
        m = self.make(learner, seed).fit(X, y)
        if learner == "RF":          # fixed summation order at prediction time (bit-reproducible)
            m.set_params(n_jobs=self.L["rf"]["predict_n_jobs"])
        return m

    def feats(self, s: str, learner: str) -> list[str]:
        return list(self.L["ols_tp"]) if learner == "OLS-TP" else list(self.sets[s])

    def design(self, df: pd.DataFrame, learner: str, feats: list[str]) -> np.ndarray:
        if learner == "OLS-TP":       # log Rs ~ bio01 + ln(bio12)
            return np.c_[tuple(np.log(df[c].values) if c in self.L["ols_tp_log"] else df[c].values
                               for c in self.L["ols_tp"])]
        return df[feats].to_numpy("float32")

    def folds(self, df: pd.DataFrame, seed: int):
        return block_folds(df.lon.values, df.lat.values, seed, self.L["cv_block_deg"], self.L["cv_folds"])

    def select(self, train_all: pd.DataFrame) -> tuple[list[dict], dict]:
        sel = []
        for s, l in self.cands:
            f = self.feats(s, l)
            a = train_all.dropna(subset=[self.T] + f).reset_index(drop=True)
            X, y = self.design(a, l, f), a[self.T].values
            r2 = []
            for seed in self.L["cv_seeds"]:
                for tr, va in self.folds(a, seed):
                    m = self.fit(l, X[tr], y[tr])
                    r2.append(r2_score(y[va], m.predict(X[va])))
            sel.append(dict(set=s, learner=l, n_pred=len(f), n_train=int(len(a)),
                            cv_r2=float(np.mean(r2)), cv_r2_sd=float(np.std(r2))))
        sel = sorted(sel, key=lambda r: -r["cv_r2"])
        best = sel[0]
        for r in sel[1:]:      # handoff rule, kept verbatim (comparisons are against the current best)
            if best["cv_r2"] - r["cv_r2"] <= self.L["tie_margin"] and r["n_pred"] < best["n_pred"]:
                best = r
        return sel, best

    def score(self, train_all, test_all, s, l, seed=None):
        f = self.feats(s, l)
        a = train_all.dropna(subset=[self.T] + f).reset_index(drop=True)
        e = test_all.dropna(subset=[self.T] + f).reset_index(drop=True)
        m = self.fit(l, self.design(a, l, f), a[self.T].values, seed)
        return a, e, f, m, m.predict(self.design(e, l, f))

    def metrics(self, y, p, lon, lat, ybase) -> dict:
        n, seed, q = self.L["bootstrap_n"], self.L["bootstrap_seed"], self.L["ci_quantiles"]
        ro, rp = np.exp(y), np.exp(p)
        return dict(n=int(len(y)), r2=float(r2_score(y, p)), ci_site=bootstrap_ci(y, p, n=n, seed=seed, q=q),
                    ci_block2=bootstrap_ci(y, p, n=n, seed=seed, lon=lon, lat=lat, deg=self.L["block_bootstrap_deg"],
                                           q=q),
                    rmse_rs=float(np.sqrt(np.mean((rp - ro) ** 2))), mae_rs=float(np.mean(np.abs(rp - ro))),
                    rmse_rs_intercept=float(np.sqrt(np.mean((np.exp(ybase) - ro) ** 2))),
                    bias_log=float(np.mean(p - y)), spearman=float(pd.Series(y).corr(pd.Series(p), method="spearman")))

    def aoa(self, a, e, f, m, best, y, p) -> dict:
        L, T = self.L, self.T
        Xa = self.design(a, best["learner"], f).astype(float)
        Xe = self.design(e, best["learner"], f).astype(float)
        mu, sd = Xa.mean(0), Xa.std(0)
        sd[sd == 0] = 1
        if best["learner"] == "OLS-TP":
            w = np.ones(Xa.shape[1])
        else:
            w = permutation_importance(m, Xa, a[T].values, n_repeats=L["aoa_perm_repeats"],
                                       random_state=L["aoa_perm_seed"]).importances_mean.clip(min=0)
            w = w / w.sum() if w.sum() > 0 else np.ones_like(w)
        Za, Ze = (Xa - mu) / sd * w, (Xe - mu) / sd * w
        dbar = cdist(Za, Za)[np.triu_indices(len(Za), 1)].mean()
        train_di = np.empty(len(Za))
        for tr, va in self.folds(a, L["aoa_cv_seed"]):
            train_di[va] = cdist(Za[va], Za[tr]).min(1) / dbar
        q1, q3 = np.quantile(train_di, L["aoa_whisker"]["quantiles"])
        thr = q3 + L["aoa_whisker"]["iqr_multiplier"] * (q3 - q1)     # upper whisker
        thr = train_di[train_di <= thr].max()
        di_e = cdist(Ze, Za).min(1) / dbar
        inside = di_e <= thr
        out = dict(threshold=float(thr), frac_inside=float(inside.mean()), n_inside=int(inside.sum()),
                   n_outside=int((~inside).sum()))
        k = L["aoa_min_group"]
        if inside.sum() > k and (~inside).sum() > k:
            base = a[T].mean()
            out["inside"] = self.metrics(y[inside], p[inside], e.lon.values[inside], e.lat.values[inside],
                                         np.full(inside.sum(), base))
            out["outside"] = self.metrics(y[~inside], p[~inside], e.lon.values[~inside], e.lat.values[~inside],
                                          np.full((~inside).sum(), base))
            rng = np.random.default_rng(L["aoa_diff_seed"])
            ii, oo = np.where(inside)[0], np.where(~inside)[0]
            diffs = []
            for _ in range(L["bootstrap_n"]):
                bi, bo = rng.choice(ii, len(ii)), rng.choice(oo, len(oo))
                diffs.append(r2_score(y[bi], p[bi]) - r2_score(y[bo], p[bo]))
            out["r2_diff_inside_minus_outside"] = dict(
                point=float(r2_score(y[inside], p[inside]) - r2_score(y[~inside], p[~inside])),
                ci=[float(np.quantile(diffs, L["ci_quantiles"][0])), float(np.quantile(diffs, L["ci_quantiles"][1]))])
        out["sq_err_by_DI_tercile"] = [float(np.mean((y - p)[g] ** 2))
                                       for g in np.array_split(np.argsort(di_e), L["di_groups"])]
        return out

    def run(self, d: pd.DataFrame, score: bool = True) -> dict:
        L, T = self.L, self.T
        train_all = d[d.continent == L["train_continent"]]
        test_all = d[d.continent == L["test_continent"]]
        sel, best = self.select(train_all)
        R = {"train": L["train_continent"], "test": L["test_continent"], "selection_table": sel, "selected": best}
        if not score:
            return R
        a, e, f, m, p = self.score(train_all, test_all, best["set"], best["learner"])
        y = e[T].values
        R["primary"] = self.metrics(y, p, e.lon.values, e.lat.values, np.full(len(y), a[T].mean()))
        if best["learner"] != "OLS-TP":
            lo, hi = L["seed_spread"]
            rs = [float(r2_score(y, self.score(train_all, test_all, best["set"], best["learner"], s)[4]))
                  for s in range(lo, hi + 1)]
            R["primary"]["seed_r2_range"] = [min(rs), max(rs)]
        else:
            R["primary"]["seed_r2_range"] = None
        R["aoa"] = self.aoa(a, e, f, m, best, y, p)
        R["all_candidates_on_test"] = []
        for s, l in self.cands:
            _a2, e2, _f2, _m2, p2 = self.score(train_all, test_all, s, l)
            R["all_candidates_on_test"].append(dict(set=s, learner=l, n=int(len(e2)), r2=float(r2_score(e2[T], p2)),
                                                    ci_site=bootstrap_ci(e2[T].values, p2, n=L["bootstrap_n"],
                                                                         seed=L["bootstrap_seed"], q=L["ci_quantiles"])))
        return R


def compare_with_locked(R: dict, locked: dict, atol: float) -> dict:
    """Differences between this re-run and the locked result. ``identical`` is True only if the same model
    is selected and every primary metric agrees to ``atol`` (``clean_test.deviation_atol``); otherwise the
    re-run is a deviation to report (ground rule 4), and the locked result stays primary."""
    out = {"selected_same": (R["selected"]["set"], R["selected"]["learner"]) ==
           (locked["selected"]["set"], locked["selected"]["learner"])}
    diffs = []
    if "primary" in R and "primary" in locked:
        for k in ["n", "r2", "rmse_rs", "mae_rs", "rmse_rs_intercept", "bias_log", "spearman"]:
            out[f"primary_{k}_diff"] = R["primary"][k] - locked["primary"][k]
            diffs.append(abs(out[f"primary_{k}_diff"]))
        for k in ["ci_site", "ci_block2"]:
            out[f"primary_{k}_diff"] = [x - y for x, y in zip(R["primary"][k], locked["primary"][k])]
            diffs += [abs(x) for x in out[f"primary_{k}_diff"]]
    out["max_abs_primary_diff"] = max(diffs) if diffs else None
    out["identical"] = bool(out["selected_same"] and diffs and max(diffs) <= atol)
    return out


def clean_test(cfg: Config) -> dict:
    lt = LockedTest(cfg)            # verifies the lock first; nothing is read or written if it is refused
    lr = cfg["clean_test"]["locked_results"]
    variants = cfg["clean_test"]["variants"]
    # features tables must be the recorded outputs of a current features run (StaleInputError otherwise)
    require_outputs(cfg, "features.json", [cfg.path("interim", f"features_v3_{t}.parquet") for t in variants])
    res = {}
    for tag in variants:
        fp = cfg.path("interim", f"features_v3_{tag}.parquet")
        d = read_table(cfg, fp)
        R = lt.run(d)
        R["lock"] = lt.lock
        R["variant"] = tag
        R["note"] = ("Reproducibility re-run of the locked test. The locked, primary result is "
                     f"{lr[tag]['file']}; it is never overwritten.")
        R["vs_locked"] = compare_with_locked(R, read_json(cfg.repo_path(lr[tag]["file"])),
                                             cfg["clean_test"]["deviation_atol"])
        write_result(cfg, R, f"clean_test_rerun_{tag}.json", inputs=["features.json"])
        res[tag] = {"selected": R["selected"], "primary_r2": R["primary"]["r2"], "n": R["primary"]["n"],
                    "identical_to_locked": R["vs_locked"]["identical"]}
    return res
