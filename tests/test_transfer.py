"""Continent transfer matrix, LOCO and the within-continent benchmark (mshi/analysis/transfer.py; Phase 2 items 1-2).

Offline and synthetic: sites on six made-up continent boxes with a known climate-Rs relation, a fake climate grid
(climate_grid reads WorldClim rasters) and a fake kNNDM with the API of mshi.analysis.knndm (tested in
tests/test_knndm.py; one test here runs the real one). The settings are lighter than configs/v3.yaml (fewer trees,
grid points, folds, seeds and bootstrap replicates); the code paths are the same. No real outcome is scored.
"""
import importlib.util
import json
import sys
import types
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import mshi.analysis as analysis_pkg
from mshi.analysis import transfer as T
from mshi.analysis.grid import cell_area_km2
from mshi.io import StaleInputError, require_current, write_result, write_table
from mshi.spatial import block_folds, bootstrap_ci
from test_robustness import sandbox

# name: (lon range, lat range, number of sites); 20 < min_test_sites (30) < 40 < within.min_sites (60) < 90
BOXES = {"Asia": ((90, 130), (20, 45), 120), "Europe": ((0, 25), (40, 60), 90),
         "North America": ((-120, -80), (30, 50), 90), "South America": ((-70, -45), (-30, 0), 40),
         "Africa": ((10, 35), (-20, 5), 20), "Oceania": ((115, 150), (-40, -15), 20)}
Q = [0.025, 0.975]
ICE_LAT = 48.0      # the fake ice sheet: North America's cells north of this latitude (review B-2)


def light(data: dict) -> None:
    """Lighter settings, plus the config keys this module needs that configs/v3.yaml does not have yet."""
    tr = data["phase2"]["transfer"]
    tr["gam"].update(penalty_criterion="aic", penalty_optimizer="nm", extrapolation="linear")
    tr["rf"].update(n_estimators=8, grid={"min_samples_leaf": [2, 8], "max_features": [0.5, 1.0]}, inner_folds=3,
                    n_jobs=1)
    tr["xgb_light"] = {**data["clean_test"]["locked"]["xgb"], "n_estimators": 12}
    tr["xgb_from"] = "phase2.transfer.xgb_light"
    data["phase2"]["within"].update(folds=2, seeds=[42, 43])
    data["phase2"]["within"]["knndm"].update(k=2, max_pred_points=50)
    data["phase2"]["bootstrap"]["n"] = 60


def synth_sites(seed: int = 0) -> pd.DataFrame:
    """Sites with log Rs = 5.0 + 0.06 MAT + 0.3 ln MAP + continent offset (+-0.05) + noise (sd 0.2); the locked
    ``continent`` column holds a value no stage may use."""
    rng = np.random.default_rng(seed)
    parts = []
    for i, (c, ((x0, x1), (y0, y1), n)) in enumerate(BOXES.items()):
        parts.append(pd.DataFrame({"continent_geo": c, "lon": rng.uniform(x0, x1, n), "lat": rng.uniform(y0, y1, n),
                                   "offset": 0.05 * (i % 3 - 1)}))
    d = pd.concat(parts, ignore_index=True)
    n = len(d)
    d["site_id"] = [f"s{i:04d}" for i in range(n)]
    d["bio01"] = 28 - 0.45 * d.lat.abs() + rng.normal(0, 1.5, n)
    d["bio12"] = np.exp(rng.normal(6.6, 0.5, n))
    for c in ("bio04", "bio05", "bio06", "bio14", "bio15", "bio17"):
        d[c] = rng.normal(50, 10, n)
    d["log_rs"] = 5.0 + 0.06 * d.bio01 + 0.3 * np.log(d.bio12) + d.offset + rng.normal(0, 0.2, n)
    d["continent"] = "not-a-continent"
    return d.drop(columns="offset")


def record_features(sand, d: pd.DataFrame) -> list:
    """Synthetic features tables recorded as outputs of a current features_analysis result."""
    paths = [write_table(d, sand.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
    write_result(sand, {"synthetic": True}, "features_analysis.json", outputs=paths)
    return paths


def install_fakes(mp, sand) -> list:
    """A recorded fetch_worldclim result, a climate grid over the boxes and a kNNDM that folds by longitude rank."""
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json")

    def climate_grid(cfg, deg, with_continent=True):
        require_current(cfg, "fetch_worldclim.json")            # as the real one (require_outputs)
        g = []
        for c, ((x0, x1), (y0, y1), _n) in BOXES.items():
            lon, lat = np.meshgrid(np.arange(x0 + deg / 2, x1, deg), np.arange(y0 + deg / 2, y1, deg))
            g.append(pd.DataFrame({"lon": lon.ravel(), "lat": lat.ravel(), "continent_geo": c,
                                   "area_km2": cell_area_km2(lat.ravel(), deg, 6371.0)}))
        return pd.concat(g, ignore_index=True)

    calls = []

    def knndm_folds(train_lonlat, pred_lonlat, k, maxp=0.5, clustering="hierarchical", seed=0, *,
                    earth_radius_km=6371.0, nk_len=100, linkage="ward.D2", ks_alpha=0.05):   # mshi.analysis.knndm's API
        calls.append(SimpleNamespace(train=np.array(train_lonlat), pred=np.array(pred_lonlat), k=k, maxp=maxp,
                                     clustering=clustering, seed=seed, radius=earth_radius_km,
                                     kw={"nk_len": nk_len, "linkage": linkage, "ks_alpha": ks_alpha}))
        rank = np.argsort(np.argsort(train_lonlat[:, 0], kind="stable"), kind="stable")
        folds = rank * k // len(rank)
        return folds, {"W": 0.25, "method": "fake", "fold_sizes": np.bincount(folds).tolist()}

    def fold_match(train_lonlat, pred_lonlat, folds, earth_radius_km=6371.0):
        return {"W": float(len(np.unique(folds))), "Gjstar_median_km": 1.0, "Gij_median_km": 2.0,
                "n_folds": int(len(np.unique(folds)))}

    def ice_sheet_mask(cfg, grid, spec):    # mshi.analysis.aoa's needs the Natural Earth files; a fake ice sheet
        calls.append(SimpleNamespace(ice_spec=spec))
        ice = grid.continent_geo.eq("North America").to_numpy() & (grid.lat.to_numpy() > ICE_LAT)
        return ice, {"n_cells": int(ice.sum()), "fake": True}

    fake = types.ModuleType("mshi.analysis.knndm")
    fake.knndm_folds, fake.fold_match = knndm_folds, fold_match
    from mshi.analysis import aoa as A
    mp.setattr(A, "ice_sheet_mask", ice_sheet_mask)
    mp.setattr(T, "climate_grid", climate_grid)
    mp.setitem(sys.modules, "mshi.analysis.knndm", fake)
    mp.setattr(analysis_pkg, "knndm", fake, raising=False)
    return calls


@pytest.fixture(scope="module", autouse=True)
def frozen_code_hash():
    """Other modules of the package may be edited while this file runs; freeze the code hash for its duration so
    results written and checked here agree."""
    from mshi import runlog
    h = runlog.code_sha256()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runlog, "code_sha256", lambda pkg_dir=None: h)
        yield h


@pytest.fixture(scope="module")
def run(cfg, tmp_path_factory):
    sand = sandbox(cfg, tmp_path_factory.mktemp("transfer"), edit=light)
    d = synth_sites()
    record_features(sand, d)
    with pytest.MonkeyPatch.context() as mp:
        calls = install_fakes(mp, sand)
        T.transfer_matrix(sand)
        T.within_continent(sand)
    tm_b, wc_b = (sand.path("results", f).read_bytes() for f in ("transfer_matrix.json", "within_continent.json"))
    return SimpleNamespace(sand=sand, d=d, knndm=calls, tm=json.loads(tm_b), wc=json.loads(wc_b), tm_b=tm_b, wc_b=wc_b)


# ---------------------------------------------------------------- metrics and bootstrap

def test_metric_formulas_on_a_hand_computed_case():
    y = np.log([100.0, 200.0, 400.0])
    p = np.log([200.0, 200.0, 200.0])
    m = T.point_metrics(y, p, np.full(3, np.log(100.0)))       # null: a training mean of log 100
    ln2 = np.log(2.0)
    # SSE = SST = 2 ln2^2; SSE_null = (0 + 1 + 4) ln2^2
    assert m["n"] == 3 and m["r2"] == pytest.approx(0.0, abs=1e-12)
    assert m["skill_vs_train_mean"] == pytest.approx(1 - 2 / 5)
    assert m["bias_log"] == pytest.approx(0.0, abs=1e-12) and m["null_bias_log"] == pytest.approx(-ln2)
    assert m["rmse_log"] == pytest.approx(ln2 * np.sqrt(2 / 3))
    assert m["rmse_rs"] == pytest.approx(np.sqrt((100.0 ** 2 + 0 + 200.0 ** 2) / 3))      # exp() back-transform
    s = T.point_metrics(y, y + 0.1, np.full(3, y.mean()))   # constant offset; the null is the test mean
    assert s["bias_log"] == pytest.approx(0.1) and s["null_bias_log"] == pytest.approx(0.0, abs=1e-12)
    assert s["r2"] == pytest.approx(1 - 3 * 0.01 / (2 * ln2 ** 2)) == pytest.approx(s["skill_vs_train_mean"])
    flat = np.full(3, 6.0)                                   # zero SST: scikit-learn's convention
    assert T.point_metrics(flat, flat, flat)["r2"] == 1.0 and T.point_metrics(flat, flat + 1, flat)["r2"] == 0.0


def test_block_bootstrap_is_bootstrap_ci_and_contains_the_point_estimate():
    rng = np.random.default_rng(3)
    lon, lat = rng.uniform(0, 20, 150), rng.uniform(40, 55, 150)
    y = 6.5 + 0.03 * lat + rng.normal(0, 0.3, 150)
    p = y + rng.normal(0.05, 0.3, 150)
    base = np.full(150, 6.4)
    reps = T.block_replicates(lon, lat, 2.0, 400, 42)
    ev, boot = T.evaluate(y, p, base, reps, Q)
    kw = dict(n=400, seed=42, lon=lon, lat=lat, deg=2.0, q=Q)
    assert ev["ci"]["r2"] == pytest.approx(bootstrap_ci(y, p, **kw), abs=1e-12)
    rmse_rs = lambda a, b: np.sqrt(np.mean((np.exp(b) - np.exp(a)) ** 2))        # noqa: E731
    skill = lambda a, b: 1 - np.mean((b - a) ** 2) / np.mean((6.4 - a) ** 2)      # noqa: E731
    assert ev["ci"]["rmse_rs"] == pytest.approx(bootstrap_ci(y, p, stat=rmse_rs, **kw), rel=1e-12)
    assert ev["ci"]["skill_vs_train_mean"] == pytest.approx(bootstrap_ci(y, p, stat=skill, **kw), abs=1e-12)
    for k in T.METRICS:
        lo, hi = ev["ci"][k]
        assert lo <= ev[k] <= hi and boot[k].shape == (400,)
    again = T.block_replicates(lon, lat, 2.0, 400, 42)
    assert np.array_equal(again.idx, reps.idx) and np.array_equal(again.rep, reps.rep)


def test_seed_mean_ci_comes_from_the_per_replicate_mean():
    rng = np.random.default_rng(4)
    lon, lat = rng.uniform(0, 30, 80), rng.uniform(0, 30, 80)
    y = rng.normal(6, 0.5, 80)
    reps = T.block_replicates(lon, lat, 2.0, 100, 1)
    evs = [T.evaluate(y, y + rng.normal(0, s, 80), np.full(80, 6.0), reps, Q) for s in (0.2, 0.4)]
    m, boot = T.seed_mean(evs, Q)
    assert m["r2"] == pytest.approx((evs[0][0]["r2"] + evs[1][0]["r2"]) / 2)
    assert m["ci"]["r2"] == T.ci((evs[0][1]["r2"] + evs[1][1]["r2"]) / 2, Q)


# ---------------------------------------------------------------- learners

def test_gam_equals_statsmodels_in_range_and_is_linear_beyond(cfg, tmp_path):
    from statsmodels.gam.api import BSplines, GLMGam
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    d = synth_sites().iloc[:150].reset_index(drop=True)
    m = T.fit_gam(spec, d)
    X = np.c_[d.bio01, np.log(d.bio12)]
    bs = BSplines(X, df=[spec.gam["df"]] * 2, degree=[spec.gam["degree"]] * 2)
    ref = GLMGam(d.log_rs.to_numpy(), exog=np.ones((len(d), 1)), smoother=bs, alpha=np.array(m.info["alpha"])).fit()
    assert np.allclose(m.predict(d), ref.fittedvalues, atol=1e-10)
    assert T.fit_gam(spec, d).info == m.info                           # penalty choice is deterministic
    far = pd.DataFrame({"bio01": np.linspace(d.bio01.max() + 1, d.bio01.max() + 20, 6), "bio12": d.bio12.median()})
    assert np.allclose(np.diff(m.predict(far), 2), 0.0, atol=1e-9)      # linear beyond the boundary knot
    lo = pd.DataFrame({"bio01": d.bio01.median(), "bio12": np.exp(np.log(d.bio12.min()) - np.array([0.5, 1.0, 1.5]))})
    assert np.allclose(np.diff(m.predict(lo), 2), 0.0, atol=1e-9)
    edge = pd.DataFrame({"bio01": [d.bio01.max(), d.bio01.max() + 1e-6], "bio12": d.bio12.median()})
    assert abs(np.diff(m.predict(edge))[0]) < 1e-4                      # continuous at the boundary


def test_ols_tp_is_the_locked_form(cfg, tmp_path):
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    d = synth_sites()
    m = T.fit_learner(spec, "OLS-TP", d)
    X = np.c_[np.ones(len(d)), d.bio01, np.log(d.bio12)]
    beta = np.linalg.lstsq(X, d.log_rs.to_numpy(), rcond=None)[0]
    assert m.info["intercept"] == pytest.approx(beta[0]) and m.info["coef"]["bio01"] == pytest.approx(beta[1])
    assert m.info["coef"]["ln bio12"] == pytest.approx(beta[2])
    assert np.allclose(m.predict(d), X @ beta)


def test_rf_tuning_never_sees_test_sites(cfg, tmp_path, monkeypatch):
    """Nested CV: in every outer fold, every forest (tuning and refit) is fit on that fold's training sites only, and
    the tuning runs inside the fold (grid points x inner folds + 1 refit per outer fold)."""
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    sub = synth_sites().query("continent_geo == 'Asia'").reset_index(drop=True)      # unique log_rs values
    events = []

    class Recording(T.RandomForestRegressor):
        def fit(self, X, y, *a, **k):
            events.append(("rf", frozenset(np.asarray(y).tolist())))
            return super().fit(X, y, *a, **k)

    real_fit = T.fit_learner

    def recording_fit(spec_, learner, train):
        events.append(("outer", frozenset(train.log_rs.tolist())))
        return real_fit(spec_, learner, train)

    monkeypatch.setattr(T, "RandomForestRegressor", Recording)
    monkeypatch.setattr(T, "fit_learner", recording_fit)
    folds = list(block_folds(sub.lon.values, sub.lat.values, 42, 5.0, 3))
    pred, base, fold, infos = T.oof_predict(spec, "RF", sub, folds)
    outer = [i for i, e in enumerate(events) if e[0] == "outer"]
    assert len(outer) == len(folds)
    per_fold = len(T.rf_grid(spec.rf)) * spec.rf["inner_folds"] + 1
    for (tr, va), i, j in zip(folds, outer, outer[1:] + [len(events)]):
        test_y = set(sub.log_rs.iloc[va])
        assert events[i][1] == frozenset(sub.log_rs.iloc[tr]) and not events[i][1] & test_y
        rfs = events[i + 1:j]
        assert len(rfs) == per_fold and all(e[0] == "rf" and e[1] <= events[i][1] for e in rfs)
    assert not np.isnan(pred).any() and set(fold) == set(range(len(folds)))
    for (tr, va) in folds:
        assert np.allclose(base[va], sub.log_rs.iloc[tr].mean())        # null = training-fold mean
    assert all({"min_samples_leaf", "max_features", "inner_cv_r2"} <= set(i) for i in infos)


def test_threaded_forest_fit_is_bit_reproducible(cfg, tmp_path):
    """Trees fit on 2 threads (rf.n_jobs, as in configs/v3.yaml) and summed on predict_n_jobs (1): the same bits."""
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=lambda x: (light(x), x["phase2"]["transfer"]["rf"].update(
        n_jobs=2))))
    d = synth_sites()
    a, b = (T.fit_learner(spec, "RF", d) for _ in range(2))
    assert a.info == b.info and np.array_equal(a.predict(d), b.predict(d))


def test_rf_with_one_inner_block_is_untunable(cfg, tmp_path):
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    d = synth_sites().iloc[:40].assign(lon=10.5, lat=45.5)
    with pytest.raises(T.Untunable, match="fewer than 2 blocks"):
        T.fit_learner(spec, "RF", d)


def test_spec_refuses_unimplemented_rules(cfg, tmp_path):
    for key, val in [("extrapolation", "constant"), ("penalty_optimizer", "basinhopping")]:
        sand = sandbox(cfg, tmp_path, edit=lambda d: (light(d), d["phase2"]["transfer"]["gam"].__setitem__(key, val)))
        with pytest.raises(ValueError, match=key):
            T.Spec.from_cfg(sand)


# ---------------------------------------------------------------- kNNDM plumbing

def test_fold_pairs_accepts_labels_pairs_and_mappings_and_checks_the_partition():
    lab = np.array([0, 1, 2, 0, 1, 2, 0])
    pairs, diag = T.fold_pairs({"folds": lab, "W": np.float64(0.2), "G": np.arange(3)}, 7)
    assert [list(te) for _, te in pairs] == [[0, 3, 6], [1, 4], [2, 5]] and diag == {"W": 0.2}
    same, _ = T.fold_pairs(iter([(tr, te) for tr, te in pairs]), 7)
    assert all(np.array_equal(a[1], b[1]) for a, b in zip(pairs, same))
    assert T.fold_pairs((list(lab), {"method": "x"}), 7)[1] == {"method": "x"}
    with pytest.raises(ValueError, match="partition"):
        T.fold_pairs([(np.arange(1, 7), np.array([0])), (np.arange(0, 6), np.array([6]))], 7)
    with pytest.raises(ValueError, match="complement"):
        T.fold_pairs([(np.arange(1, 4), np.array([0])), (np.array([0]), np.arange(1, 7))], 7)
    with pytest.raises(ValueError, match="fold labels"):
        T.fold_pairs(lab[:5], 7)


def test_a_knndm_refusal_is_recorded_and_the_block_splits_stand(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=light)
    sub = synth_sites().query("continent_geo == 'Europe'").sort_values("site_id").reset_index(drop=True)

    def refuse(*a, **k):
        raise RuntimeError("no grid value satisfies maxp")

    def match(train_lonlat, pred_lonlat, folds, earth_radius_km=6371.0):
        return {"W": 1.0, "Gjstar_median_km": 1.0, "Gij_median_km": 2.0}
    splits, summary, kn = T.cv_splits(sand, sub, np.c_[np.arange(10.0), np.full(10, 50.0)], refuse, match)
    seeds = sand["phase2"]["within"]["seeds"]
    assert list(splits) == [("blocks", s) for s in seeds] and set(summary) == {f"blocks_{s}" for s in seeds}
    assert kn["diagnostics"] == {"error": "RuntimeError: no grid value satisfies maxp"}


def test_prediction_domain_draws_cells_by_area_or_uniformly():
    lat = np.r_[np.full(50, 0.25), np.full(50, 70.25), np.full(30, 10.25)]
    g = pd.DataFrame({"lon": np.arange(130.0), "lat": lat, "continent_geo": ["A"] * 100 + ["B"] * 30,
                      "area_km2": cell_area_km2(lat, 0.5, 6371.0)})
    K = {"max_pred_points": 4000, "seed": 42, "grid_deg": 0.5, "pred_weight": "area"}
    a = T.prediction_domain(g, "A", K)
    assert len(a) == 4000 and (a[:, 0] < 100).all() and np.array_equal(a, T.prediction_domain(g, "A", K))
    share = (a[:, 1] > 50).mean()                          # cells at 70 N have cos(70) / cos(0) = 0.34 of the area
    w = np.cos(np.radians(70.25)) / (np.cos(np.radians(70.25)) + np.cos(np.radians(0.25)))
    assert share == pytest.approx(w, abs=0.03)
    u = T.prediction_domain(g, "A", {**K, "pred_weight": "none", "max_pred_points": 25})
    assert len(u) == 25 and len(np.unique(u[:, 0])) == 25 and (np.diff(u[:, 0]) > 0).all()
    assert len(T.prediction_domain(g, "B", {**K, "pred_weight": "none"})) == 30
    with pytest.raises(ValueError, match="no 0.5-degree"):
        T.prediction_domain(g, "C", K)
    with pytest.raises(ValueError, match="pred_weight"):
        T.prediction_domain(g, "A", {**K, "pred_weight": "latitude"})


# ---------------------------------------------------------------- stages

def test_transfer_matrix_structure(run):
    R, nmin = run.tm, run.sand["phase2"]["min_test_sites"]
    assert R["exploratory"] is True and R["method"] and R["continent_column"] == "continent_geo"
    assert R["sites"]["by_continent"] == {c: v[2] for c, v in BOXES.items()} and R["sites"]["n_used"] == 380
    learners, conts = R["learners"], R["continents"]
    trains = [c for c, v in BOXES.items() if v[2] >= nmin]                       # Asia, Europe, N and S America
    rows = R["main"] + R["supplementary"]
    assert len([r for r in rows if r["table"] == "pairwise"]) == len(trains) * 5 * len(learners)
    assert len([r for r in rows if r["table"] == "loco"]) == len(conts) * len(learners)
    assert all(r["n_test"] >= nmin for r in R["main"]) and all(r["n_test"] < nmin for r in R["supplementary"])
    assert {r["test"] for r in R["supplementary"]} == {"Africa", "Oceania"}
    assert {(s["train"], s["n_train"]) for s in R["skipped"]} == {(c, v[2]) for c, v in BOXES.items() if v[2] < nmin}
    for r in rows:
        assert set(T.METRICS) <= set(r) and set(r["ci"]) == set(T.METRICS)
        assert all(lo <= hi for lo, hi in r["ci"].values())
        assert r["n_test"] == BOXES[r["test"]][2]
        assert r["n_train"] == (sum(v[2] for c, v in BOXES.items() if c != r["test"]) if r["table"] == "loco"
                                else BOXES[r["train"]][2])
    loco = {(r["learner"], r["test"]): r for r in rows if r["table"] == "loco"}
    assert loco["OLS-TP", "Asia"]["r2"] > 0.2 and loco["GAM", "Europe"]["r2"] > 0.2     # the known relation transfers
    rf = [r["fit"] for r in rows if r["learner"] == "RF"]
    assert all(f["min_samples_leaf"] in (2, 8) and f["max_features"] in (0.5, 1.0) for f in rf)
    assert R["learner_settings"]["XGB"]["n_estimators"] == 12 and R["versions"]["xgboost"]
    tp = pd.read_parquet(run.sand.path("interim", "transfer_predictions_qc.parquet"))
    assert len(tp) == sum(r["n_test"] for r in rows)
    one = loco["XGB", "Europe"]
    g = tp[(tp.table == "loco") & (tp.test == "Europe") & (tp.learner == "XGB")]
    assert T.point_metrics(g.obs_log.to_numpy(), g.pred_log.to_numpy(), g.null_log.to_numpy())["r2"] == pytest.approx(
        one["r2"], abs=1e-12)
    assert set(R["_outputs"]) == {"interim:transfer_predictions_qc.parquet", "figures:phase2/transfer_matrix.png",
                                  "figures:phase2/transfer_matrix.pdf"}
    assert set(R["_inputs"]) == {"features_analysis.json"}


def test_within_continent_benchmark(run):
    W, R, tm = run.sand["phase2"]["within"], run.wc, run.tm
    trains = {c for c, v in BOXES.items() if v[2] >= run.sand["phase2"]["min_test_sites"]}
    assert R["exploratory"] is True and R["method"]
    assert list(R["continents"]) == [c for c, v in BOXES.items() if v[2] >= W["min_sites"]]   # Asia, Europe, N America
    assert {s["continent"] for s in R["skipped"]} == {"South America", "Africa", "Oceania"}
    assert set(R["_inputs"]) == {"features_analysis.json", "transfer_matrix.json", "fetch_worldclim.json"}
    assert set(R["_outputs"]) == {"interim:within_predictions_qc.parquet", "figures:phase2/within_continent.png",
                                  "figures:phase2/within_continent.pdf"}
    loco = {(r["learner"], r["test"]): r for r in tm["main"] + tm["supplementary"] if r["table"] == "loco"}
    wp = pd.read_parquet(run.sand.path("interim", "within_predictions_qc.parquet"))
    tp = pd.read_parquet(run.sand.path("interim", "transfer_predictions_qc.parquet"))
    B = run.sand["phase2"]["bootstrap"]
    for c, e in R["continents"].items():
        assert e["n"] == BOXES[c][2] and e["splits"]["blocks_42"]["n_folds"] == W["folds"]
        assert e["splits"]["knndm_42"]["W_km"] == W["knndm"]["k"] and e["knndm"]["Gij_median_km"] == 2.0
        assert e["transfer_n_train"]["LOCO"] == sum(v[2] for o, v in BOXES.items() if o != c)
        sizes = e["splits"]["knndm_42"]["test_sizes"]
        assert e["knndm"]["diagnostics"] == {"W": 0.25, "method": "fake", "fold_sizes": sizes}
        for learner, L in e["learners"].items():
            per = L["blocks"]["per_seed"]
            assert [p["seed"] for p in per] == W["seeds"]
            assert L["blocks"]["seed_mean"]["r2"] == pytest.approx(np.mean([p["r2"] for p in per]))
            assert L["transfer"]["LOCO"]["r2"] == loco[learner, c]["r2"]          # same predictions, same bootstrap
            assert L["transfer"]["LOCO"]["ci"] == loco[learner, c]["ci"]
            assert set(L["penalty_r2"]) == {"LOCO"} | (trains - {c})
            pen = L["penalty_r2"]["LOCO"]
            assert set(pen) == {"blocks", "blocks_first_seed", "knndm"}
            assert pen["blocks"]["point"] == pytest.approx(L["blocks"]["seed_mean"]["r2"] - L["transfer"]["LOCO"]["r2"])
            assert pen["knndm"]["point"] == pytest.approx(L["knndm"]["r2"] - L["transfer"]["LOCO"]["r2"])
    # the paired CI, recomputed from the two prediction tables with the same resampled blocks
    c, learner = "Europe", "GAM"
    sites = run.d[run.d.continent_geo == c].sort_values("site_id")
    reps = T.block_replicates(sites.lon.to_numpy(), sites.lat.to_numpy(), B["block_deg"], B["n"], B["seed"])

    def boot_r2(g):
        g = g.set_index("site_id").loc[sites.site_id]
        return T.metric_arrays(g.obs_log, g.pred_log, g.null_log, reps.idx, reps.rep, reps.n)["r2"]
    w = np.mean([boot_r2(wp[(wp.continent == c) & (wp.learner == learner) & (wp.scheme == "blocks") & (wp.seed == s)])
                 for s in W["seeds"]], axis=0)
    lo = boot_r2(tp[(tp.table == "loco") & (tp.test == c) & (tp.learner == learner)])
    assert R["continents"][c]["learners"][learner]["penalty_r2"]["LOCO"]["blocks"]["ci"] == T.ci(w - lo, B["quantiles"])
    assert R["continents"]["Asia"]["learners"]["OLS-TP"]["blocks"]["seed_mean"]["r2"] > 0.1


def test_knndm_gets_the_continents_sites_and_its_grid_cells(run):
    K = run.sand["phase2"]["within"]["knndm"]
    folds = [c for c in run.knndm if hasattr(c, "train")]
    assert len(folds) == 3
    for call, c in zip(folds, ["Asia", "Europe", "North America"]):
        (x0, x1), (y0, y1), n = BOXES[c]
        assert call.train.shape == (n, 2) and len(call.pred) == K["max_pred_points"]
        assert ((call.pred[:, 0] > x0) & (call.pred[:, 0] < x1) & (call.pred[:, 1] > y0) & (call.pred[:, 1] < y1)).all()
        if c == "North America":                                       # no point on the (fake) ice sheet
            assert (call.pred[:, 1] < ICE_LAT).all()
        assert (call.k, call.maxp, call.clustering, call.seed) == (K["k"], K["maxp"], K["clustering"], K["seed"])
        assert call.radius == run.sand["site_build"]["earth_radius_km"]
        assert call.kw == {k: K[k] for k in ("nk_len", "linkage", "ks_alpha")}          # configured, passed through
        sites = run.d[run.d.continent_geo == c].sort_values("site_id")
        assert np.array_equal(call.train, np.c_[sites.lon, sites.lat])


def test_knndm_prediction_domain_leaves_out_the_ice_sheets(run):
    """Review B-2 (D-P2-16): the cells of phase2.aoa.ice_sheets are left out of the kNNDM prediction domain, and the
    result says how many."""
    spec = [c.ice_spec for c in run.knndm if hasattr(c, "ice_spec")]
    assert spec == [run.sand["phase2"]["aoa"]["ice_sheets"]]
    (x0, x1), (_y0, y1), _n = BOXES["North America"]
    deg = run.sand["phase2"]["within"]["knndm"]["grid_deg"]
    n_ice = int(round((x1 - x0) / deg)) * int(np.sum(np.arange(_y0 + deg / 2, y1, deg) > ICE_LAT))
    dom = run.wc["prediction_domain"]
    assert dom["exclude_ice_sheets"] is True and dom["ice_cells_by_continent"] == {"North America": n_ice}
    assert dom["n_cells_used"] == dom["n_cells"] - n_ice and dom["ice_sheets"] == spec[0]


def test_gam_penalty_search_is_capped_and_a_linear_truth_gives_the_linear_fit(cfg, tmp_path):
    """Review B-1 (D-P2-15): statsmodels' own search ran to alpha 1e13-1e16 on these data, where its fit penalises
    the linear trend; capped at gam.alpha_max inside the criterion, a linear truth gives the least-squares line."""
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    cap = spec.gam["alpha_max"]
    for seed in (1, 4, 5):
        rng, n = np.random.default_rng(seed), 200
        d = pd.DataFrame({"bio01": rng.uniform(-5, 25, n), "bio12": np.exp(rng.uniform(5, 8, n))})
        d["log_rs"] = 5 + 0.05 * d.bio01 + 0.3 * np.log(d.bio12) + rng.normal(0, 0.2, n)
        m = T.fit_gam(spec, d)
        assert max(m.info["alpha"]) <= cap * (1 + 1e-12) and m.info["at_alpha_max"] == [True, True]
        X = np.c_[np.ones(n), d.bio01, np.log(d.bio12)]
        line = X @ np.linalg.lstsq(X, d.log_rs, rcond=None)[0]
        assert np.abs(m.predict(d) - line).max() < 1e-5


def test_stages_refuse_stale_inputs(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=light)
    d = synth_sites()
    qc = record_features(sand, d)[0]
    write_table(d.assign(log_rs=d.log_rs + 1), qc)                       # the table changed after it was recorded
    with pytest.raises(StaleInputError, match="features_analysis_qc.parquet changed after the run"):
        T.transfer_matrix(sand)
    assert not sand.path("results", "transfer_matrix.json").exists()
    record_features(sand, d)
    require_current(sand, "features_analysis.json")
    tp = write_table(pd.DataFrame({"x": [1]}), sand.path("interim", "transfer_predictions_qc.parquet"))
    write_result(sand, {"main": [], "supplementary": []}, "transfer_matrix.json", outputs=[tp],
                 inputs=["features_analysis.json"])
    write_table(pd.DataFrame({"x": [2]}), tp)
    with pytest.raises(StaleInputError, match="transfer_predictions_qc.parquet changed after the run"):
        T.within_continent(sand)
    other = sandbox(cfg, tmp_path, edit=lambda x: (light(x), x["phase2"]["bootstrap"].__setitem__("n", 61)))
    with pytest.raises(StaleInputError, match="different config"):        # recorded under another config
        T.transfer_matrix(other)


def test_sites_are_complete_listed_positive_and_sorted(cfg, tmp_path):
    """Every learner is scored on the same sites, in site_id order whatever the table's row order (so results do
    not depend on it: everything downstream is a deterministic function of this table)."""
    spec = T.Spec.from_cfg(sandbox(cfg, tmp_path, edit=light))
    d = synth_sites()
    d.loc[0, "bio05"] = np.nan                       # a missing c8 predictor
    d.loc[1, "bio12"] = 0.0                          # ln bio12 undefined
    d.loc[2, "continent_geo"] = None                 # no geographic continent
    d.loc[3, "continent_geo"] = "Antarctica"         # not in phase2.continents
    conts = list(BOXES)
    a, info = T.prepare_sites(spec, d, conts)
    b, info_b = T.prepare_sites(spec, d.sample(frac=1.0, random_state=1), conts)
    pd.testing.assert_frame_equal(a, b)
    assert info == info_b and info["n_used"] == len(d) - 4 and list(a.site_id) == sorted(a.site_id)
    assert info["n_missing_values"] == 1 and info["n_nonpositive_log_predictor"] == 1
    assert info["continent_not_listed"] == {"Antarctica": 1, "missing": 1}
    assert "continent" not in a                      # the locked column is not carried
    with pytest.raises(ValueError, match="not unique"):
        T.prepare_sites(spec, pd.concat([d, d.iloc[[5]]]), conts)


@pytest.mark.skipif(importlib.util.find_spec("mshi.analysis.knndm") is None, reason="mshi.analysis.knndm absent")
def test_the_real_knndm_module_fits_the_call(cfg, tmp_path):
    """The call and the return value handling match mshi.analysis.knndm itself (not the fake)."""
    from mshi.analysis import knndm
    sand = sandbox(cfg, tmp_path, edit=light)
    sub = synth_sites().query("continent_geo == 'Europe'").sort_values("site_id").reset_index(drop=True)
    rng = np.random.default_rng(0)
    dom = np.c_[rng.uniform(-10, 40, 300), rng.uniform(35, 70, 300)]
    splits, summary, kn = T.cv_splits(sand, sub, dom, knndm.knndm_folds, knndm.fold_match)
    K = sand["phase2"]["within"]["knndm"]
    assert ("knndm", K["seed"]) in splits or "error" in kn["diagnostics"]
    for name, f in summary.items():
        assert f["n_folds"] >= 1 and sum(f["test_sizes"]) == len(sub) and f["W_km"] >= 0
    if ("knndm", K["seed"]) in splits:
        assert kn["diagnostics"]["W"] == pytest.approx(summary[f"knndm_{K['seed']}"]["W_km"])


def test_two_runs_give_byte_identical_results(run):
    """Last in the file: re-runs both stages in the shared sandbox. The result JSONs record the SHA-256 of the
    prediction tables and figures, so equal bytes cover those too."""
    with pytest.MonkeyPatch.context() as mp:
        install_fakes(mp, run.sand)
        T.transfer_matrix(run.sand)
        T.within_continent(run.sand)
    assert run.sand.path("results", "transfer_matrix.json").read_bytes() == run.tm_b
    assert run.sand.path("results", "within_continent.json").read_bytes() == run.wc_b
