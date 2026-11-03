"""Why the original US R² was low: E4/E4b re-run cleanly (mshi/analysis/us_r2.py; Phase 2 item 5).

Offline and synthetic: sites in Asia, in the Asia box outside Asia, in and around the US bounding box (with sites on
its edges, a western-Aleutian site in both the Asia box and North America, and one with no continent), and a records
table built to exercise the single-record rule. log Rs follows a known climate relation, so the test-set spread is
small inside the box and large outside it. Settings are lighter than configs/v3.yaml (bootstrap replicates, XGB seed
spread); the code paths are the same. No real outcome is scored.
"""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from mshi.analysis import transfer as T
from mshi.analysis import us_r2 as U
from mshi.io import StaleInputError, write_result, write_table
from mshi.spatial import bootstrap_ci
from test_robustness import sandbox

Q = [0.025, 0.975]
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
# (continent_geo, country, lon range, lat range, number of sites)
GROUPS = [("Asia", "China", (90, 130), (5, 55), 70),
          ("Europe", "Finland", (26, 40), (50, 60), 12),                        # in the Asia box, not in Asia
          ("North America", "United States of America", (-120, -80), (30, 48), 50),     # US bounding box
          ("North America", "Canada", (-110, -90), (52, 60), 18),               # outside the box, north
          ("North America", "Panama", (-84, -79), (8, 10), 14),                 # outside the box, south
          ("South America", "Brazil", (-70, -45), (-30, 0), 10)]                # in no region
# (continent_geo, country, lon, lat): edges of the US bounding box [-125, -66, 24, 50] and overlaps
POINTS = [("North America", "United States of America", 175.0, 52.0),   # western Aleutians: Asia box and N America
          ("North America", "United States of America", -125.0, 40.0),  # west edge: inside
          ("North America", "Mexico", -66.0, 24.0),                     # south-east corner: inside
          ("North America", "Canada", -100.0, 50.0),                    # north edge: inside
          ("North America", "Canada", -100.0, 50.0001),                 # just north: outside
          ("North America", "United States of America", -125.0001, 40.0),   # just west: outside
          (None, None, -70.0, 30.0)]                                    # no continent: in the box only
REPO_ONLY = 8                    # extra Asian sites whose records all fail a QC filter (repo variant only)
N_ASIA, N_ASIA_BOX = 70, 70 + 12 + 1
N_BOX, N_NA, N_OUT = 50 + 3 + 1, 50 + 18 + 14 + 6, 18 + 14 + 3


@pytest.fixture(scope="module", autouse=True)
def frozen_code_hash():
    """Other modules of the package may be edited while this file runs; freeze the code hash for its duration so
    results written and checked here agree."""
    from mshi import runlog
    h = runlog.code_sha256()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runlog, "code_sha256", lambda pkg_dir=None: h)
        yield h


def settings(data: dict, **us) -> None:
    """Lighter test settings: a 3-seed XGB spread and 200 bootstrap replicates (configs/v3.yaml has the real ones,
    and the same continents)."""
    data["phase2"]["us_r2"].update({"train_continent": "Asia", "test_continent": "North America",
                                    "xgb_seed_spread": [0, 2], **us})
    data["phase2"]["bootstrap"]["n"] = 200


def synth(seed: int = 0, max_records: int = 3) -> SimpleNamespace:
    """Records and the features tables of both variants. Site log Rs = 5.0 + 0.06 MAT + 0.3 ln MAP + site effect (sd
    0.2); records add noise (sd 0.3). Every 9th site has a COSORE record; every 6th has an extra record that fails a
    QC filter (repo variant only); REPO_ONLY Asian sites have only such records. SRDB rows are shuffled numbers, so
    table order is not row order. The locked ``continent`` column holds a value no stage may use."""
    rng = np.random.default_rng(seed)
    parts = [pd.DataFrame({"continent_geo": c, "country": k, "lon": rng.uniform(*x, n), "lat": rng.uniform(*y, n)})
             for c, k, x, y, n in GROUPS]
    parts.append(pd.DataFrame(POINTS, columns=["continent_geo", "country", "lon", "lat"]))
    parts.append(pd.DataFrame({"continent_geo": "Asia", "country": "China", "lon": rng.uniform(90, 130, REPO_ONLY),
                               "lat": rng.uniform(20, 45, REPO_ONLY)}))
    s = pd.concat(parts, ignore_index=True)
    n = len(s)
    s["bio01"] = 28 - 0.45 * s.lat.abs() + rng.normal(0, 1.0, n)
    s["bio12"] = np.exp(rng.normal(6.6, 0.2, n))
    for c in ("bio04", "bio05", "bio06", "bio14", "bio15", "bio17"):
        s[c] = rng.normal(50, 10, n)
    mu = 5.0 + 0.06 * s.bio01 + 0.3 * np.log(s.bio12) + rng.normal(0, 0.2, n)
    rows = iter(rng.permutation(np.arange(100, 100 + 6 * n)))
    recs = []
    for i in range(n):
        repo_only = i >= n - REPO_ONLY
        m = int(rng.integers(1, max_records + 1))
        for j in range(m + (i % 6 == 0 and max_records > 1)):
            cosore = i % 9 == 0 and j == 0 and max_records > 1
            row = np.nan if cosore else float(next(rows))
            recs.append({"rec_id": f"cosore_d{i:03d}" if cosore else f"srdb_{int(row)}",
                         "src": "cosore" if cosore else "srdb", "srdb_row": row, "site": i,
                         "lat": s.lat[i], "lon": s.lon[i], "continent_geo": s.continent_geo[i],
                         "log_rs": mu[i] + rng.normal(0, 0.3), "qc": not repo_only and j < m})
    r = pd.DataFrame(recs).sample(frac=1.0, random_state=seed).reset_index(drop=True)     # table order != row order
    r["site_id_qc"] = np.where(r.qc, "v3aqc_" + r.site.map("{:05d}".format), None)
    r["site_id_repo"] = "v3arepo_" + r.site.map("{:05d}".format)
    tables = {}
    for v in ("qc", "repo"):
        g = r[r[f"site_id_{v}"].notna()].groupby("site")
        f = s.loc[g.size().index].copy()
        f["site_id"] = [f"v3a{v}_{i:05d}" for i in f.index]
        f["log_rs"] = g.log_rs.mean()
        f["n_rec"] = g.size()
        f["n_cosore"] = g.src.apply(lambda x: int((x == "cosore").sum()))
        f["continent"] = "not-a-continent"
        tables[v] = f.reset_index(drop=True)
    return SimpleNamespace(records=r.drop(columns=["site", "qc"]), features=tables)


def record(sand, tabs: SimpleNamespace) -> dict:
    """The synthetic tables, recorded as outputs of current features_analysis and build_sites_analysis results."""
    paths = {v: write_table(f, sand.path("interim", f"features_analysis_{v}.parquet"))
             for v, f in tabs.features.items()}
    write_result(sand, {"synthetic": True}, "features_analysis.json", outputs=list(paths.values()))
    rp = write_table(tabs.records, sand.path("derived", "records_analysis.parquet"))
    write_result(sand, {"synthetic": True}, "build_sites_analysis.json", outputs=[rp])
    return {**paths, "records": rp}


def expected_single(rec: pd.DataFrame, variant: str) -> pd.Series:
    """The original rule written independently: COSORE first (lowest rec_id), then the lowest SRDB row."""
    r = rec[rec[f"site_id_{variant}"].notna()].copy()
    r["k"] = (r.src != "cosore").astype(int)
    r["row"] = r.srdb_row.fillna(-1)
    return r.sort_values(["k", "row", "rec_id"]).groupby(f"site_id_{variant}").log_rs.first()


@pytest.fixture(scope="module")
def staged(cfg, tmp_path_factory):
    sand = sandbox(cfg, tmp_path_factory.mktemp("us_r2"), edit=settings)
    tabs = synth()
    record(sand, tabs)
    out = U.us_r2(sand)
    b = sand.path("results", "us_r2.json").read_bytes()
    return SimpleNamespace(sand=sand, tabs=tabs, out=out, R=json.loads(b), b=b)


def _row(R: dict, **k) -> dict:
    hits = [r for r in R["rows"] if all(r[a] == b for a, b in k.items())]
    assert len(hits) == 1, k
    return hits[0]


OUT = "North America outside the US bounding box"


# ---------------------------------------------------------------- metrics and the block bootstrap

def test_metric_formulas_on_a_hand_computed_case():
    y = np.log([100.0, 200.0, 400.0])
    p = np.log([200.0, 200.0, 200.0])
    m = U.point_metrics(y, p, np.full(3, np.log(100.0)))         # null: a training mean of log 100
    ln2 = np.log(2.0)
    # SSE = SST = 2 ln2^2 (the test mean is log 200); SSE_null = (0 + 1 + 4) ln2^2
    assert m["r2"] == pytest.approx(0.0, abs=1e-12)
    assert m["rmse_log"] == pytest.approx(ln2 * np.sqrt(2 / 3)) and m["sd_log"] == pytest.approx(ln2 * np.sqrt(2 / 3))
    assert m["rmse_null_log"] == pytest.approx(ln2 * np.sqrt(5 / 3))
    assert m["skill_vs_train_mean"] == pytest.approx(1 - 2 / 5)
    assert m["bias_log"] == pytest.approx(0.0, abs=1e-12) and m["null_bias_log"] == pytest.approx(-ln2)
    assert m["rmse_rs"] == pytest.approx(np.sqrt((100.0 ** 2 + 0 + 200.0 ** 2) / 3))       # exp() back-transform
    assert m["rmse_null_rs"] == pytest.approx(np.sqrt((0 + 100.0 ** 2 + 300.0 ** 2) / 3))
    rng = np.random.default_rng(1)
    y, p = rng.normal(6.5, 0.6, 40), rng.normal(6.5, 0.6, 40)
    m = U.point_metrics(y, p, np.full(40, 6.2))
    assert m["r2"] == pytest.approx(r2_score(y, p), abs=1e-12)
    assert m["r2"] == pytest.approx(1 - (m["rmse_log"] / m["sd_log"]) ** 2, abs=1e-12)          # the R2 identity
    assert m["rmse_null_log"] ** 2 == pytest.approx(m["sd_log"] ** 2 + m["null_bias_log"] ** 2, abs=1e-12)
    assert m["sd_log"] == pytest.approx(np.std(y)) and m["bias_log"] == pytest.approx(np.mean(p - y))
    flat = np.full(3, 6.0)                                       # zero SST: scikit-learn's convention
    assert U.point_metrics(flat, flat, flat)["r2"] == 1.0 and U.point_metrics(flat, flat + 1, flat)["r2"] == 0.0


def test_block_bootstrap_has_the_draws_of_bootstrap_ci():
    rng = np.random.default_rng(3)
    lon, lat = rng.uniform(-120, -80, 150), rng.uniform(25, 50, 150)
    y = 6.5 + 0.03 * lat + rng.normal(0, 0.3, 150)
    p = y + rng.normal(0.05, 0.3, 150)
    base = np.full(150, 6.4)
    reps = T.block_replicates(lon, lat, 2.0, 300, 42)
    ev, boot = U.evaluate(y, p, base, reps, Q)
    kw = dict(n=300, seed=42, lon=lon, lat=lat, deg=2.0, q=Q)
    assert ev["ci"]["r2"] == pytest.approx(bootstrap_ci(y, p, **kw), abs=1e-12)
    assert ev["ci"]["rmse_log"] == pytest.approx(bootstrap_ci(y, p, stat=lambda a, b: np.sqrt(np.mean((b - a) ** 2)),
                                                              **kw), rel=1e-12)
    assert ev["ci"]["sd_log"] == pytest.approx(bootstrap_ci(y, p, stat=lambda a, b: np.std(a), **kw), rel=1e-12)
    assert ev["ci"]["rmse_null_log"] == pytest.approx(
        bootstrap_ci(y, p, stat=lambda a, b: np.sqrt(np.mean((6.4 - a) ** 2)), **kw), rel=1e-12)
    for k in U.METRICS:
        lo, hi = ev["ci"][k]
        assert lo <= ev[k] <= hi and boot[k].shape == (300,)


# ---------------------------------------------------------------- settings and regions

def test_region_masks_on_boundary_cases(cfg, tmp_path):
    S = U.Settings.from_cfg(sandbox(cfg, tmp_path, edit=settings))
    trains, tests = U.regions(S)
    assert [r.name for r in trains] == ["Asia", "Asia box"]
    assert [r.name for r in tests] == ["US bounding box", "North America", OUT]
    pts = pd.DataFrame(POINTS + [("Asia", "Japan", 140.0, 36.0), ("Asia", "Russia", 180.0, 65.0),
                                 ("Asia", "Russia", np.nan, 65.0), ("Europe", "Estonia", 25.0, 58.0),
                                 ("Europe", "Spain", 24.9999, 40.0), ("Oceania", "Fiji", 179.0, -10.0)],
                       columns=["continent_geo", "country", "lon", "lat"])
    pts["continent"] = "North America"            # the locked column: never used
    box, na, out = (r.mask(pts) for r in tests)
    asia, abox = (r.mask(pts) for r in trains)
    #            Aleut  W edge corner N edge north west  none   Japan  180E   NaN    25E    <25E   Fiji
    assert box.tolist() == [0, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0]
    assert na.tolist() == [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    assert out.tolist() == [1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    assert asia.tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0]
    assert abox.tolist() == [1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1]
    ov = U.overlaps(pts.assign(site_id=[f"p{i}" for i in range(len(pts))]), trains, tests)
    assert {(o["train"], o["test"]): o["n"] for o in ov} == {
        ("Asia", "US bounding box"): 0, ("Asia", "North America"): 0, ("Asia", OUT): 0,
        ("Asia box", "US bounding box"): 0, ("Asia box", "North America"): 1, ("Asia box", OUT): 1}
    assert [o["examples"] for o in ov if o["n"]][0] == [{"site_id": "p0", "lon": 175.0, "lat": 52.0,
                                                          "continent_geo": "North America"}]
    assert tests[2].describe() == ("continent_geo == 'North America' and outside -125 <= lon <= -66 and "
                                   "24 <= lat <= 50")
    assert trains[1].describe() == "inside 25 <= lon <= 180 and -10 <= lat <= 80 (any continent)"


@pytest.mark.parametrize("edit,match", [
    (lambda d: d["phase2"]["us_r2"].pop("train_continent"), r"lacks \['train_continent'\]"),
    (lambda d: d["phase2"]["us_r2"].update(asia_box=[180.0, 25.0, -10.0, 80.0]), "asia_box must be"),
    (lambda d: d["phase2"]["us_r2"].update(us_box=[-125.0, -66.0, 24.0]), "us_box must be"),
    (lambda d: d["phase2"]["us_r2"].update(us_box=[-125.0, -66.0, 24.0, 95.0]), "us_box must be"),
    (lambda d: d["phase2"]["us_r2"].update(learners=["XGB", "RF"]), "learners"),
    (lambda d: d["phase2"]["us_r2"].update(learners=[]), "learners"),
    (lambda d: d["phase2"]["us_r2"].update(train_continent="Atlantis"), "train_continent 'Atlantis'"),
    (lambda d: d["phase2"]["us_r2"].update(test_continent="Asia"), "must differ"),
    (lambda d: d["phase2"]["us_r2"].update(xgb_seed_spread=[3, 1]), "xgb_seed_spread"),
    (lambda d: d["site_build"].update(variants=["qc", "strict"]), "site_build.variants"),
    (lambda d: d["phase2"].update(variant="other"), "phase2.variant"),
])
def test_settings_are_checked_before_anything_is_read(cfg, tmp_path, edit, match):
    """No upstream result exists in this sandbox: a check that ran after reading would raise StaleInputError."""
    sand = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), edit(d)))
    with pytest.raises(ValueError, match=match):
        U.us_r2(sand)
    assert not sand.path("results", "us_r2.json").exists()


def test_box_check():
    assert U.check_box("b", [-125, -66, 24, 50]) == (-125.0, -66.0, 24.0, 50.0)
    for bad in ([170, -170, 50, 60], [10, 10, 0, 1], [0, 1, 50, 40], [-181, 0, 0, 1]):
        with pytest.raises(ValueError, match="antimeridian"):
            U.check_box("b", bad)


# ---------------------------------------------------------------- the single-record target

def _tiny():
    d = pd.DataFrame({"site_id": ["A", "B", "C", "D"], "n_rec": [3, 2, 2, 1]})
    rec = pd.DataFrame([("srdb_10", "srdb", 10.0, "A", 1.0), ("srdb_9", "srdb", 9.0, "A", 2.0),
                        ("srdb_100", "srdb", 100.0, "A", 3.0),       # numeric order: srdb_9, not srdb_10
                        ("srdb_3", "srdb", 3.0, "B", 4.0), ("cosore_x", "cosore", np.nan, "B", 5.0),   # COSORE first
                        ("cosore_b", "cosore", np.nan, "C", 6.0), ("cosore_a", "cosore", np.nan, "C", 7.0),
                        ("srdb_7", "srdb", 7.0, "D", 8.0),
                        ("srdb_1", "srdb", 1.0, "E", 9.0),           # a site not used (not in d)
                        ("srdb_2", "srdb", 2.0, None, 9.5)],         # not in this variant
                       columns=["rec_id", "src", "srdb_row", "site_id_qc", "log_rs"])
    d["log_rs"] = d.site_id.map(rec.groupby("site_id_qc").log_rs.mean())
    return d, rec


def test_single_record_rule():
    d, rec = _tiny()
    out, info = U.single_record(rec, d, "qc", "log_rs")
    assert out.site_id.tolist() == ["A", "B", "C", "D"]
    assert out.rec_id.tolist() == ["srdb_9", "cosore_x", "cosore_a", "srdb_7"]
    assert out.log_rs.tolist() == [2.0, 5.0, 7.0, 8.0] and out.row.tolist() == [9, -1, -1, 7]
    assert info["records_of_sites_not_used"] == 1 and info["n_chosen_cosore"] == 2
    assert info["n_sites_with_several_records"] == 3 and info["n_sites_with_several_cosore_records"] == 1
    for seed in range(3):                                           # the table's row order does not matter
        again, _ = U.single_record(rec.sample(frac=1.0, random_state=seed), d.sample(frac=1.0, random_state=seed)
                                   .sort_values("site_id"), "qc", "log_rs")
        pd.testing.assert_frame_equal(again, out)
    no_row, _ = U.single_record(rec.drop(columns="srdb_row"), d, "qc", "log_rs")     # the column is optional
    pd.testing.assert_frame_equal(no_row, out)


@pytest.mark.parametrize("change,match", [
    (lambda d, r: d.__setitem__("n_rec", [3, 2, 2, 2]), "record count or mean"),
    (lambda d, r: r.__setitem__("log_rs", r.log_rs.where(r.rec_id != "srdb_7", 8.5)), "record count or mean"),
    (lambda d, r: r.__setitem__("srdb_row", r.srdb_row.where(r.rec_id != "srdb_9", 90.0)), "srdb_row differs"),
    (lambda d, r: r.__setitem__("rec_id", r.rec_id.where(r.rec_id != "srdb_9", "srdb_9a")), "srdb_<row>"),
    (lambda d, r: r.__setitem__("site_id_qc", r.site_id_qc.where(r.site_id_qc != "D", "E")), "no record"),
    (lambda d, r: r.__setitem__("src", r.src.where(r.rec_id != "srdb_7", "fluxnet")), "unknown source"),
    (lambda d, r: r.__setitem__("rec_id", r.rec_id.where(r.rec_id != "srdb_7", "srdb_3")), "not unique"),
])
def test_single_record_refuses_tables_that_do_not_match(change, match):
    d, rec = _tiny()
    change(d, rec)
    with pytest.raises(ValueError, match=match):
        U.single_record(rec, d, "qc", "log_rs")


# ---------------------------------------------------------------- learners

def test_xgb_parameters_come_from_transfer_xgb_from(cfg, tmp_path):
    """Review D-1: us_r2 and aoa_sensitivity take the XGB block named by phase2.transfer.xgb_from, as
    transfer_matrix does, so a row the tables share cannot differ between them."""
    from mshi.analysis import aoa

    def alt(data):
        settings(data)
        data["phase2"]["transfer"]["xgb_alt"] = {**data["clean_test"]["locked"]["xgb"], "max_depth": 2}
        data["phase2"]["transfer"]["xgb_from"] = "phase2.transfer.xgb_alt"
    sand = sandbox(cfg, tmp_path, edit=alt)
    S = U.Settings.from_cfg(sand)
    assert S.xgb["max_depth"] == 2 and S.describe()["XGB"]["from"] == "phase2.transfer.xgb_alt"
    assert T.Spec.from_cfg(sand).xgb == S.xgb and "phase2.transfer.xgb_alt" in U.method_text(S)
    X = np.random.default_rng(0).normal(size=(40, 3)).astype("float32")
    assert aoa.fit_xgb(sand, X, X[:, 0].astype(float)).get_params()["max_depth"] == 2
    assert "phase2.transfer.xgb_alt" in aoa.method_text(sand)


def test_learners_are_the_specified_ones(cfg, tmp_path):
    """OLS-TP is least squares on bio01 and ln bio12; XGB is XGBRegressor(**clean_test.locked.xgb, random_state =
    phase2.transfer.xgb_seed) on c8 as float32; both equal mshi.analysis.transfer's learners on the same sites."""
    import xgboost
    sand = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), d["phase2"]["transfer"].update(
        xgb_from="clean_test.locked.xgb")))
    S = U.Settings.from_cfg(sand)
    d, _ = U.prepare_sites(synth().features["qc"], S)
    tr = d[d.continent_geo.eq("Asia")]
    y = tr.log_rs.to_numpy()
    p, info = U.fit_predict(S, "OLS-TP", tr, y, d)
    X = np.c_[np.ones(len(tr)), tr.bio01, np.log(tr.bio12)]
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    assert np.allclose(p, np.c_[np.ones(len(d)), d.bio01, np.log(d.bio12)] @ beta)
    assert info["intercept"] == pytest.approx(beta[0]) and info["coef"]["ln bio12"] == pytest.approx(beta[2])
    px, ix = U.fit_predict(S, "XGB", tr, y, d)
    direct = xgboost.XGBRegressor(**cfg["clean_test"]["locked"]["xgb"], random_state=cfg["phase2"]["transfer"][
        "xgb_seed"]).fit(tr[C8].to_numpy("float32"), y).predict(d[C8].to_numpy("float32"))
    assert np.array_equal(px, direct.astype(float)) and ix == {"random_state": cfg["phase2"]["transfer"]["xgb_seed"]}
    p5, i5 = U.fit_predict(S, "XGB", tr, y, d, seed=5)
    assert i5 == {"random_state": 5} and not np.array_equal(p5, px)
    spec = T.Spec.from_cfg(sand)
    assert np.array_equal(T.fit_learner(spec, "XGB", tr.assign(log_rs=y)).predict(d), px)
    assert np.allclose(T.fit_learner(spec, "OLS-TP", tr.assign(log_rs=y)).predict(d), p, atol=1e-12)
    with pytest.raises(ValueError, match="unknown learner"):
        U.fit_predict(S, "GAM", tr, y, d)


def test_sites_are_complete_positive_and_sorted(cfg, tmp_path):
    S = U.Settings.from_cfg(sandbox(cfg, tmp_path, edit=settings))
    f = synth().features["qc"]
    f.loc[0, "bio05"] = np.nan                     # a missing c8 predictor
    f.loc[1, "bio12"] = 0.0                        # ln bio12 undefined
    f.loc[2, "log_rs"] = np.nan                    # no target
    a, info = U.prepare_sites(f, S)
    b, _ = U.prepare_sites(f.sample(frac=1.0, random_state=2), S)
    pd.testing.assert_frame_equal(a, b)
    assert info == {"n_table": len(f), "n_used": len(f) - 3, "n_missing_values": 2, "n_nonpositive_log_predictor": 1}
    assert list(a.site_id) == sorted(a.site_id) and "continent" not in a        # the locked column is not carried
    with pytest.raises(ValueError, match="not unique"):
        U.prepare_sites(pd.concat([f, f.iloc[[5]]]), S)
    with pytest.raises(ValueError, match="lacks"):
        U.prepare_sites(f.drop(columns="continent_geo"), S)


# ---------------------------------------------------------------- the stage

def test_stage_result_structure(staged):
    R, sand = staged.R, staged.sand
    assert R["exploratory"] is True and R["method"] and R["continent_column"] == "continent_geo"
    assert list(R["variants"]) == ["qc", "repo"] and R["primary_variant"] == "qc"
    assert R["variants"]["qc"]["primary"] is True and R["variants"]["repo"]["primary"] is False
    assert R["variants"]["qc"]["filters"].startswith("coordinate check + QC filters")
    assert "QC filters" not in R["variants"]["repo"]["filters"] and "E4 and E4b" in R["variants"]["repo"]["filters"]
    assert "geodesic" in R["variants"]["repo"]["filters"]
    assert len(R["rows"]) == 2 * 2 * 2 * 2 * 3 and len(R["target_effect"]) == 2 * 2 * 2 * 3 and R["skipped"] == []
    assert staged.out == {"n_rows": 48, "n_target_effects": 24, "n_skipped": 0}
    assert set(R["_inputs"]) == {"features_analysis.json", "build_sites_analysis.json"}
    assert set(R["_outputs"]) == {"figures:phase2/us_r2.png", "figures:phase2/us_r2.pdf"}
    import xgboost
    assert R["versions"]["xgboost"] == xgboost.__version__
    assert R["learner_settings"]["XGB"]["random_state"] == sand["phase2"]["transfer"]["xgb_seed"]
    for r in R["rows"]:
        assert set(U.METRICS) <= set(r) and set(r["ci"]) == set(U.METRICS)
        assert all(lo <= hi for lo, hi in r["ci"].values())
        assert r["r2"] == pytest.approx(1 - (r["rmse_log"] / r["sd_log"]) ** 2, abs=1e-12)
        assert ("seed_spread" in r) == (r["learner"] == "XGB")
        if r["learner"] == "XGB":
            assert r["seed_spread"]["seeds"] == [0, 2]
            assert r["seed_spread"]["r2"]["min"] <= r["r2"] <= r["seed_spread"]["r2"]["max"]      # seed 0 is in it
    png, pdf = (sand.path("figures", "phase2", f"us_r2.{x}") for x in ("png", "pdf"))
    assert png.stat().st_size > 10_000 and pdf.stat().st_size > 5_000


def test_counts_overlaps_and_composition(staged):
    R = staged.R
    for v, extra in (("qc", 0), ("repo", REPO_ONLY)):
        V = R["variants"][v]
        n_all = sum(g[-1] for g in GROUPS) + len(POINTS) + extra
        assert V["sites"] == {"n_table": n_all, "n_used": n_all, "n_missing_values": 0,
                              "n_nonpositive_log_predictor": 0}
        reg = V["regions"]
        assert reg["Asia"]["n"] == N_ASIA + extra and reg["Asia box"]["n"] == N_ASIA_BOX + extra
        assert reg["Asia box"]["by_continent_geo"] == {"Asia": N_ASIA + extra, "Europe": 12, "North America": 1}
        assert reg["US bounding box"]["n"] == N_BOX and reg["North America"]["n"] == N_NA and reg[OUT]["n"] == N_OUT
        assert reg["US bounding box"]["by_continent_geo"] == {"North America": N_BOX - 1, "missing": 1}
        assert reg[OUT]["by_country"] == {"Canada": 19, "Panama": 14, "United States of America": 2}
        assert reg[OUT]["relative_to_box"] == {"south": 14, "north": 20, "west_or_east": 1}
        ov = {(o["train"], o["test"]): o for o in V["overlaps"]}
        assert {k: o["n"] for k, o in ov.items() if o["n"]} == {("Asia box", "North America"): 1, ("Asia box", OUT): 1}
        assert ov["Asia box", OUT]["examples"][0]["lon"] == 175.0
        for tr, n_train in (("Asia", N_ASIA + extra), ("Asia box", N_ASIA_BOX + extra)):
            for te, n_test in (("US bounding box", N_BOX), ("North America", N_NA), (OUT, N_OUT)):
                excl = int(tr == "Asia box" and te != "US bounding box")      # the Aleutian site
                for r in (x for x in R["rows"] if (x["variant"], x["train"], x["test"]) == (v, tr, te)):
                    assert (r["n_train"], r["n_test"]) == (n_train, n_test - excl)
                    assert r["n_test_excluded_as_training_sites"] == excl
                    assert r["below_min_test_sites"] is False
        sr = V["single_record"]
        assert sr["n_sites"] == n_all and sr["records_of_sites_not_used"] == 0
        assert sr["n_chosen_cosore"] == sum(1 for i in range(n_all) if i % 9 == 0)    # repo-only sites come last


def test_rows_recomputed_from_scratch(staged):
    """One OLS-TP row per target, recomputed with scikit-learn and mshi.spatial.bootstrap_ci from the input tables."""
    R, tabs, sand = staged.R, staged.tabs, staged.sand
    B = sand["phase2"]["bootstrap"]
    f = tabs.features["qc"].sort_values("site_id").reset_index(drop=True)
    single = expected_single(tabs.records, "qc")
    for target, y_all in (("site_mean", f.log_rs.to_numpy()), ("single_record", single.loc[f.site_id].to_numpy())):
        train = f.continent_geo.eq("Asia").to_numpy()
        test = (f.continent_geo.eq("North America") & ~(f.lon.between(-125, -66) & f.lat.between(24, 50))).to_numpy()
        X = np.c_[f.bio01, np.log(f.bio12)]
        p = LinearRegression().fit(X[train], y_all[train]).predict(X[test])
        y, base = y_all[test], y_all[train].mean()
        r = _row(R, variant="qc", target=target, train="Asia", test=OUT, learner="OLS-TP")
        assert r["n_test"] == test.sum() and r["train_mean_log"] == pytest.approx(base, abs=1e-12)
        assert r["r2"] == pytest.approx(r2_score(y, p), abs=1e-12)
        assert r["rmse_log"] == pytest.approx(np.sqrt(np.mean((p - y) ** 2)), abs=1e-12)
        assert r["sd_log"] == pytest.approx(np.std(y), abs=1e-12)
        assert r["rmse_null_log"] == pytest.approx(np.sqrt(np.mean((base - y) ** 2)), abs=1e-12)
        assert r["rmse_rs"] == pytest.approx(np.sqrt(np.mean((np.exp(p) - np.exp(y)) ** 2)), rel=1e-12)
        kw = dict(n=B["n"], seed=B["seed"], lon=f.lon.to_numpy()[test], lat=f.lat.to_numpy()[test],
                  deg=B["block_deg"], q=B["quantiles"])
        assert r["ci"]["r2"] == pytest.approx(bootstrap_ci(y, p, **kw), abs=1e-12)
    assert not np.allclose(single.loc[f.site_id].to_numpy(), f.log_rs.to_numpy())    # the targets differ


def test_test_set_spread_drives_r2(staged):
    """The known relation: the US bounding box spans a narrow climate range, North America outside it a wide one, so
    R² is lower in the box although the RMSE is about the same (E4b's point)."""
    for learner in ("OLS-TP", "XGB"):
        for train in ("Asia", "Asia box"):
            box, out = (_row(staged.R, variant="qc", target="site_mean", train=train, test=t, learner=learner)
                        for t in ("US bounding box", OUT))
            assert out["sd_log"] > 1.5 * box["sd_log"] and out["r2"] > box["r2"] + 0.3
            if learner == "OLS-TP":          # the true functional form: the same error in both regions
                assert abs(out["rmse_log"] - box["rmse_log"]) < 0.1 * box["rmse_log"]
    ols = _row(staged.R, variant="qc", target="site_mean", train="Asia", test=OUT, learner="OLS-TP")
    assert ols["fit"]["coef"]["bio01"] == pytest.approx(0.06, abs=0.03)          # the relation is recovered


def test_target_effect_is_paired(staged):
    R, sand = staged.R, staged.sand
    B = sand["phase2"]["bootstrap"]
    for e in R["target_effect"]:
        a, b = (_row(R, variant=e["variant"], target=t, train=e["train"], test=e["test"], learner=e["learner"])
                for t in U.TARGETS)
        for m in U.EFFECT_METRICS:
            assert e[m]["site_mean"] == a[m] and e[m]["single_record"] == b[m]
            assert e[m]["difference"] == pytest.approx(a[m] - b[m], abs=1e-15)
        assert ("seed_spread_r2_difference" in e) == (e["learner"] == "XGB")
    # recompute one paired CI from the two OLS-TP fits and shared replicates
    tabs = staged.tabs
    f = tabs.features["qc"].sort_values("site_id").reset_index(drop=True)
    targets = {"site_mean": f.log_rs.to_numpy(), "single_record": expected_single(tabs.records, "qc").loc[
        f.site_id].to_numpy()}
    train, test = f.continent_geo.eq("Asia").to_numpy(), f.lon.between(-125, -66).to_numpy() & f.lat.between(
        24, 50).to_numpy()
    reps = T.block_replicates(f.lon.to_numpy()[test], f.lat.to_numpy()[test], B["block_deg"], B["n"], B["seed"])
    X = np.c_[f.bio01, np.log(f.bio12)]
    boot = {}
    for t, y in targets.items():
        p = LinearRegression().fit(X[train], y[train]).predict(X[test])
        boot[t] = U.metric_arrays(y[test], p, np.full(test.sum(), y[train].mean()), reps.idx, reps.rep, reps.n)
    e = next(x for x in R["target_effect"] if (x["variant"], x["train"], x["test"], x["learner"]) ==
             ("qc", "Asia", "US bounding box", "OLS-TP"))
    assert e["r2"]["ci"] == pytest.approx(T.ci(boot["site_mean"]["r2"] - boot["single_record"]["r2"], B["quantiles"]),
                                          abs=1e-12)


def test_one_record_per_site_makes_the_targets_identical(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=settings)
    tabs = synth(seed=4, max_records=1)
    record(sand, tabs)
    U.us_r2(sand)
    R = json.loads(sand.path("results", "us_r2.json").read_text())
    assert all(V["single_record"]["n_sites_with_several_records"] == 0 for V in R["variants"].values())
    for e in R["target_effect"]:
        for m in U.EFFECT_METRICS:
            assert e[m]["difference"] == 0.0 and e[m]["ci"] == [0.0, 0.0]
        if "seed_spread_r2_difference" in e:
            assert e["seed_spread_r2_difference"] == {"seeds": [0, 2], "min": 0.0, "mean": 0.0, "max": 0.0}


def test_small_training_sets_are_skipped_and_small_test_sets_flagged(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), d["phase2"].update(min_test_sites=N_ASIA + 1)))
    tabs = synth()
    record(sand, tabs)
    U.us_r2(sand)
    R = json.loads(sand.path("results", "us_r2.json").read_text())
    sk = [(s["variant"], s["target"], s["train"]) for s in R["skipped"]]
    assert sk == [("qc", t, "Asia") for t in U.TARGETS]           # repo: Asia has 70 + 8 sites, enough
    assert {r["train"] for r in R["rows"] if r["variant"] == "qc"} == {"Asia box"}
    assert all(r["below_min_test_sites"] == (r["n_test"] < N_ASIA + 1) for r in R["rows"])
    assert any(r["below_min_test_sites"] for r in R["rows"])


def test_a_smoke_sized_subset_runs_and_skips_small_training_sets(cfg, tmp_path):
    """As in smoke runs: the site tables are a subset, the records table is not. Records of the other sites are left
    out and counted; training sets below min_test_sites are skipped; the result and the figure are still written."""
    sand = sandbox(cfg, tmp_path, edit=settings)
    tabs = synth()
    sub = SimpleNamespace(records=tabs.records, features={v: f.sample(n=40, random_state=1).reset_index(drop=True)
                                                         for v, f in tabs.features.items()})
    record(sand, sub)
    out = U.us_r2(sand)
    R = json.loads(sand.path("results", "us_r2.json").read_text())
    assert out == {"n_rows": 0, "n_target_effects": 0, "n_skipped": 2 * 2 * 2} and R["rows"] == []
    assert {(s["variant"], s["target"], s["train"]) for s in R["skipped"]} == {
        (v, t, tr) for v in ("qc", "repo") for t in U.TARGETS for tr in ("Asia", "Asia box")}
    for v in ("qc", "repo"):
        n_rec = tabs.records[f"site_id_{v}"].notna().sum()
        used = tabs.records[f"site_id_{v}"].isin(sub.features[v].site_id).sum()
        assert R["variants"][v]["single_record"]["records_of_sites_not_used"] == n_rec - used > 0
    assert set(R["_outputs"]) == {"figures:phase2/us_r2.png", "figures:phase2/us_r2.pdf"}


def test_refuses_stale_inputs(cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=settings)
    tabs = synth()
    paths = record(sand, tabs)
    write_table(tabs.features["qc"].assign(log_rs=tabs.features["qc"].log_rs + 1), paths["qc"])   # changed after
    with pytest.raises(StaleInputError, match="features_analysis_qc.parquet changed after the run"):
        U.us_r2(sand)
    record(sand, tabs)
    write_table(tabs.records.assign(log_rs=tabs.records.log_rs + 1), paths["records"])
    with pytest.raises(StaleInputError, match="records_analysis.parquet changed after the run"):
        U.us_r2(sand)
    assert not sand.path("results", "us_r2.json").exists()
    record(sand, tabs)
    other = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), d["phase2"]["bootstrap"].__setitem__("n", 201)))
    with pytest.raises(StaleInputError, match="different config"):        # recorded under another config
        U.us_r2(other)
    bad = copy.deepcopy(tabs)                                             # current, but the tables do not match
    bad.records.loc[bad.records.rec_id == bad.records.rec_id.iloc[0], "log_rs"] += 0.5
    record(sand, bad)
    with pytest.raises(ValueError, match="differs from the site table"):
        U.us_r2(sand)
    assert not sand.path("results", "us_r2.json").exists()


def test_row_order_of_the_inputs_does_not_matter(staged, cfg, tmp_path):
    sand = sandbox(cfg, tmp_path, edit=settings)
    tabs = staged.tabs
    shuffled = SimpleNamespace(records=tabs.records.sample(frac=1.0, random_state=7),
                               features={v: f.sample(frac=1.0, random_state=8) for v, f in tabs.features.items()})
    record(sand, shuffled)
    U.us_r2(sand)
    R = json.loads(sand.path("results", "us_r2.json").read_text())
    for k in ("rows", "target_effect", "variants", "skipped", "_outputs"):     # _outputs: the same figure bytes
        assert R[k] == staged.R[k], k


def test_asia_to_north_america_rows_equal_the_transfer_matrix(cfg, tmp_path):
    """Trained on Asia and tested on North America (qc variant, site-mean target), the rows are the transfer matrix's
    pairwise rows: the same sites, models and bootstrap replicates, so the same number never differs between tables."""
    sand = sandbox(cfg, tmp_path, edit=lambda d: (settings(d), d["phase2"]["transfer"].update(
        learners=["OLS-TP", "XGB"], xgb_from="clean_test.locked.xgb")))
    record(sand, synth())
    U.us_r2(sand)
    T.transfer_matrix(sand)
    R = json.loads(sand.path("results", "us_r2.json").read_text())
    M = json.loads(sand.path("results", "transfer_matrix.json").read_text())
    for learner in ("OLS-TP", "XGB"):
        t = next(r for r in M["main"] + M["supplementary"]
                 if (r["table"], r["train"], r["test"], r["learner"]) == ("pairwise", "Asia", "North America", learner))
        u = _row(R, variant="qc", target="site_mean", train="Asia", test="North America", learner=learner)
        assert (u["n_train"], u["n_test"]) == (t["n_train"], t["n_test"])
        for k in T.METRICS:
            assert u[k] == pytest.approx(t[k], abs=1e-12), k
            assert u["ci"][k] == pytest.approx(t["ci"][k], abs=1e-12), k


def test_two_runs_give_byte_identical_results(staged):
    """Re-runs the stage in the shared sandbox; the result records the figure's SHA-256, so equal bytes cover it."""
    U.us_r2(staged.sand)
    assert staged.sand.path("results", "us_r2.json").read_bytes() == staged.b
