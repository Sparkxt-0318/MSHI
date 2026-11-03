"""Area-of-applicability sensitivity (mshi/analysis/aoa.py; Phase 2 item 4).

Offline and synthetic: sites on made-up continent boxes with a known climate-Rs relation; a fake climate grid on the
lattice climate_grid uses (the real one reads WorldClim rasters), with an "Antarctica" south of 65 S, unassigned cells
south of 60 S and on islands, and a "Greenland" box; a fake geographic_continent (the real one reads Natural Earth).
The settings are lighter than configs/v3.yaml (coarser grid, fewer trees, permutation repeats and bootstrap
replicates), plus the config keys this module needs that configs/v3.yaml does not have yet. No real outcome is scored.
"""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from mshi.analysis import aoa as AOA
from mshi.analysis.grid import cell_area_km2
from mshi.io import StaleInputError, read_table, require_current, write_result, write_table
from test_robustness import sandbox

GRID_DEG = 2.5
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
# sites: name -> (lon range, lat range, number of sites)
BOXES = {"Asia": ((90, 130), (20, 45), 120), "Europe": ((0, 25), (40, 60), 90),
         "North America": ((-120, -80), (30, 50), 90), "South America": ((-70, -45), (-30, 0), 40),
         "Africa": ((10, 35), (-20, 5), 20), "Oceania": ((115, 150), (-40, -15), 20)}
GREENLAND = ((-50, -25), (60, 80))
# grid: the site boxes plus (lon range, lat range, continent_geo); None = no geographic continent
EXTRA_CELLS = [((-120, -80), (50, 70), "North America"), (GREENLAND[0], GREENLAND[1], "North America"),
               ((-180, 180), (-90, -65), "Antarctica"), ((-60, -40), (-65, -60), None), ((160, 170), (0, 10), None),
               ((-10, 10), (15, 30), "Africa")]
# configuration keys this module needs that configs/v3.yaml does not have yet (reported to the integrator)
NEW_KEYS = {
    "threshold_rules": {"whisker_max": {"rule": "whisker", "quantiles": [0.25, 0.75], "iqr_multiplier": 1.5},
                        "q95": {"rule": "quantile", "q": 0.95}},
    "lat_bands": {"edges": [-90.0, -60.0, -23.5, 23.5, 50.0, 66.5, 90.0],
                  "labels": ["Antarctic", "S temperate", "Tropics", "N temperate", "N boreal", "Arctic"]},
    "ice_sheets": {"continent_geo": ["Antarctica"], "south_of_lat": -60.0, "subunits": ["Greenland"]},
    "transfer_check": {"train": "Asia", "test": "North America"},
}


def light(data: dict) -> None:
    """Lighter settings, plus the keys of NEW_KEYS."""
    data["phase2"]["aoa"].update(copy.deepcopy(NEW_KEYS), grid_deg=GRID_DEG, perm_repeats=3)
    data["clean_test"]["locked"]["xgb"]["n_estimators"] = 40          # sandbox copy; this stage checks no lock
    data["phase2"]["bootstrap"]["n"] = 50


def climate(lon, lat) -> pd.DataFrame:
    """Smooth made-up bioclim fields: colder and drier away from the equator."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    alat = np.abs(lat)
    bio01 = 28.0 - 0.5 * alat
    bio12 = 300.0 + 1500.0 * np.exp(-(lat / 25.0) ** 2) + 3.0 * np.mod(lon, 60.0)
    return pd.DataFrame({"bio01": bio01, "bio04": 200.0 + 15.0 * alat, "bio05": bio01 + 10.0,
                         "bio06": bio01 - 15.0 - 0.2 * alat, "bio12": bio12, "bio14": 0.02 * bio12,
                         "bio15": 40.0 + 0.3 * alat, "bio17": 0.1 * bio12})


def synth_sites(seed: int = 0) -> pd.DataFrame:
    """Sites with log Rs = 5 + 0.04 MAT + 0.3 ln MAP + noise; two sites outside the listed continents and one without
    bio12. The locked ``continent`` column holds a value no stage may use."""
    rng = np.random.default_rng(seed)
    parts = [pd.DataFrame({"continent_geo": c, "lon": rng.uniform(x0, x1, n), "lat": rng.uniform(y0, y1, n)})
             for c, ((x0, x1), (y0, y1), n) in BOXES.items()]
    parts.append(pd.DataFrame({"continent_geo": "Antarctica", "lon": [-60.0, 40.0], "lat": [-70.0, -68.0]}))
    d = pd.concat(parts, ignore_index=True)
    n = len(d)
    clim = climate(d.lon, d.lat)
    noise = rng.normal(0.0, 1.0, (n, len(C8))) * np.array([1.0, 20.0, 1.0, 1.0, 60.0, 2.0, 2.0, 8.0])
    d[C8] = clim[C8].to_numpy() + noise
    d["bio12"] = d.bio12.abs() + 50.0
    d["log_rs"] = 5.0 + 0.04 * d.bio01 + 0.3 * np.log(d.bio12) + rng.normal(0.0, 0.2, n)
    d["site_id"] = [f"s{i:04d}" for i in rng.permutation(n)]
    d.loc[5, "bio12"] = np.nan
    d["continent"] = "not-a-continent"
    return d


def _box_cells(lon_range, lat_range, deg: float) -> tuple[np.ndarray, np.ndarray]:
    lon, lat = np.meshgrid(np.arange(lon_range[0] + deg / 2, lon_range[1], deg),
                           np.arange(lat_range[0] + deg / 2, lat_range[1], deg))
    return lon.ravel(), lat.ravel()


def fake_grid(deg: float) -> pd.DataFrame:
    parts = []
    boxes = [(lo, la, c) for c, (lo, la, _n) in BOXES.items()] + EXTRA_CELLS
    for lo, la, c in boxes:
        lon, lat = _box_cells(lo, la, deg)
        parts.append(pd.concat([pd.DataFrame({"lon": lon, "lat": lat}), climate(lon, lat)], axis=1)
                     .assign(continent_geo=c, area_km2=cell_area_km2(lat, deg, 6371.0)))
    g = pd.concat(parts, ignore_index=True)
    assert not g.duplicated(["lon", "lat"]).any()
    return g


def in_box(lon, lat, box) -> np.ndarray:
    (x0, x1), (y0, y1) = box
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return (lon >= x0) & (lon < x1) & (lat >= y0) & (lat < y1)


def record_features(sand, d: pd.DataFrame) -> list:
    """Synthetic features tables recorded as outputs of a current features_analysis result."""
    paths = [write_table(d, sand.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
    write_result(sand, {"synthetic": True}, "features_analysis.json", outputs=paths)
    return paths


def install_fakes(mp, sand) -> list:
    """A recorded fetch_worldclim result, the fake climate grid and a fake geographic_continent (records its calls)."""
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json")
    calls = []

    def climate_grid(cfg, deg, with_continent=True):
        require_current(cfg, "fetch_worldclim.json")            # as the real one (require_outputs)
        return fake_grid(deg)

    def geographic_continent(cfg, lon, lat, su=None):
        calls.append(np.c_[lon, lat])
        green = in_box(lon, lat, GREENLAND)
        return pd.DataFrame({"continent_geo": np.where(green, "North America", "elsewhere"),
                             "geo_subunit": np.where(green, "Greenland", "Somewhere"),
                             "geo_subunit_admin": np.where(green, "Greenland", "Somewhere"),
                             "geo_subunit_km": 0.0})

    mp.setattr(AOA, "climate_grid", climate_grid)
    mp.setattr(AOA, "geographic_continent", geographic_continent)
    mp.setattr(AOA, "subunits", fake_subunits)
    return calls


def fake_subunits(cfg) -> pd.DataFrame:
    """The columns of mshi.geo.subunits that ice_sheet_mask reads (the real one reads Natural Earth)."""
    return pd.DataFrame({"SUBUNIT": ["Greenland", "Canada", "Svalbard", "Russia"],
                         "ADMIN": ["Greenland", "Canada", "Norway", "Russia"],
                         "continent_geo": ["North America", "North America", "Europe", "Europe"]})


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
def staged(cfg, tmp_path_factory):
    sand = sandbox(cfg, tmp_path_factory.mktemp("aoa"), edit=light)
    d = synth_sites()
    record_features(sand, d)
    with pytest.MonkeyPatch.context() as mp:
        calls = install_fakes(mp, sand)
        summary = AOA.aoa_sensitivity(sand)
    raw = sand.path("results", "aoa_sensitivity.json").read_bytes()
    table = read_table(sand, sand.path("interim", "aoa_di_grid.parquet"))
    return SimpleNamespace(sand=sand, d=d, calls=calls, summary=summary, raw=raw, res=json.loads(raw), table=table)


# ---------------------------------------------------------------- DI, thresholds and weights

def test_di_equals_a_hand_computed_value_on_three_points():
    s, h = np.sqrt(1.5), 1 / np.sqrt(2)
    base = np.array([[-s, -h], [s, -h], [0.0, np.sqrt(2.0)]])   # column means 0, population SDs 1: an equilateral
    X = base * [10.0, 3.0] + [100.0, -5.0]                      # triangle of side sqrt(6); standardising undoes this
    sp = AOA.di_space(X, np.array([0.5, 0.5]))
    assert sp.dbar == pytest.approx(np.sqrt(6.0) / 2)
    # the centroid is sqrt(2) from every vertex: DI = sqrt(2) / sqrt(6) = 1 / sqrt(3), whatever the common weight
    assert sp.di(np.array([[100.0, -5.0]]))[0] == pytest.approx(1 / np.sqrt(3.0))
    assert sp.di(X) == pytest.approx(np.zeros(3), abs=1e-12)
    # only the first predictor weighted: points at -s, s, 0, mean pairwise distance 4s/3; a query at s/2 is s/2 from
    # its nearest point, so DI = 3/8 whatever its second predictor
    sp1 = AOA.di_space(X, np.array([1.0, 0.0]))
    assert sp1.di(np.array([[100.0 + 10.0 * s / 2, 1e6]]))[0] == pytest.approx(3 / 8)
    # one fold per point: each point's nearest other point is a side away, so every training DI is 1
    folds = [(np.array([1, 2]), np.array([0])), (np.array([0, 2]), np.array([1])), (np.array([0, 1]), np.array([2]))]
    assert AOA.training_di(sp, folds) == pytest.approx(np.ones(3))


def test_training_di_uses_only_the_other_folds():
    X = np.array([[0.0], [1.0], [10.0], [11.0]])
    sp = AOA.di_space(X, np.array([1.0]))
    assert sp.dbar * np.std(X) == pytest.approx(7.0)            # pairs 1, 10, 11, 9, 10, 1 (raw units): mean 7
    folds = [(np.array([2, 3]), np.array([0, 1])), (np.array([0, 1]), np.array([2, 3]))]
    # nearest points of the other fold are 10, 9, 9, 10 away (not the within-fold neighbour 1 away)
    assert AOA.training_di(sp, folds) == pytest.approx(np.array([10, 9, 9, 10]) / 7.0)
    with pytest.raises(ValueError, match="do not hold out"):
        AOA.training_di(sp, folds[:1])
    with pytest.raises(ValueError, match="no training points"):
        AOA.training_di(sp, [(np.array([], int), np.arange(4))])


def test_whisker_and_q95_thresholds_on_a_known_distribution():
    W = {"rule": "whisker", "quantiles": [0.25, 0.75], "iqr_multiplier": 1.5}
    Q = {"rule": "quantile", "q": 0.95}
    C = {**W, "rule": "fence_capped"}
    di = np.arange(1, 101) / 100.0                              # 0.01 ... 1.00
    # linear quantiles: Q1 = 0.2575, Q3 = 0.7525, fence 1.495 above the maximum: nothing is an outlier
    t = AOA.threshold(di, W)
    assert t["value"] == 1.0 and t["fence"] == pytest.approx(1.495) and t["n_train_above_fence"] == 0
    assert AOA.threshold(di, Q)["value"] == pytest.approx(0.9505)
    assert AOA.threshold(di, C)["value"] == 1.0                 # CAST 1.2.0: min(fence, max) = max here
    out = np.r_[di, 5.0, 10.0][np.random.default_rng(0).permutation(102)]
    # n = 102: Q1 = 0.2625, Q3 = 0.7675, fence = 0.7675 + 1.5 x 0.505 = 1.525: the outlier-removed maximum is 1.00
    t = AOA.threshold(out, W)
    assert t == {"value": 1.0, "fence": pytest.approx(1.525), "n_train_above_fence": 2, "train_di_max": 10.0}
    assert AOA.threshold(out, Q)["value"] == pytest.approx(0.9695)   # position 95.95: 0.96 + 0.95 x 0.01
    assert AOA.threshold(out, C)["value"] == pytest.approx(1.525)     # CAST: the fence itself, above whisker_max
    with pytest.raises(ValueError, match="unknown threshold rule"):
        AOA.threshold(di, {"rule": "max"})


def test_weights_none_are_equal_and_permutation_weights_are_clipped_and_normalised():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 4))
    y = 2.0 * X[:, 0] + X[:, 1] + rng.normal(0.0, 0.1, 300)
    w, fallback = AOA.importance_weights("none", None, X, y, 3, 0)
    assert np.array_equal(w, np.full(4, 0.25)) and not fallback
    w, fallback = AOA.importance_weights("permutation", LinearRegression().fit(X, y), X, y, 5, 0)
    assert not fallback and w.sum() == pytest.approx(1.0) and (w >= 0).all()
    assert w[0] > w[1] > max(w[2], w[3]) and max(w[2], w[3]) < 0.01      # noise columns: about 0 (clipped at 0)
    w, fallback = AOA.importance_weights("permutation", DummyRegressor().fit(X, y), X, y, 5, 0)
    assert fallback and np.array_equal(w, np.full(4, 0.25))              # no positive importance: equal weights
    # equal weights give the unweighted standardised distance (the DI ignores a common factor)
    q = rng.normal(size=(5, 4))
    Z = (X - X.mean(0)) / X.std(0)
    d = np.sqrt(((((q - X.mean(0)) / X.std(0))[:, None, :] - Z[None]) ** 2).sum(-1)).min(1)
    pairs = np.sqrt(((Z[:, None, :] - Z[None]) ** 2).sum(-1))[np.triu_indices(300, 1)].mean()
    assert AOA.di_space(X, np.full(4, 0.25)).di(q) == pytest.approx(d / pairs)
    with pytest.raises(ValueError, match="unknown weights"):
        AOA.importance_weights("shap", None, X, y, 3, 0)


# ---------------------------------------------------------------- shares, bands and ice sheets

def test_area_and_flux_shares_on_a_toy_grid():
    outside = np.array([False, True, False, True])
    area = np.array([1.0, 2.0, 3.0, 4.0])
    rs = np.array([100.0, 200.0, 300.0, 400.0])                 # flux = Rs x area: 100, 400, 900, 1600
    cont = np.array(["A", "A", "B", "B"], dtype=object)
    rep = AOA.domain_shares(outside, area, rs * area, {"by_continent_geo": cont})
    assert rep["area_frac_outside"] == pytest.approx(6 / 10) and rep["flux_frac_outside"] == pytest.approx(2000 / 3000)
    assert (rep["n_cells"], rep["n_cells_outside"]) == (4, 2)
    assert rep["by_continent_geo"]["A"]["area_frac_outside"] == pytest.approx(2 / 3)
    assert rep["by_continent_geo"]["B"]["area_frac_outside"] == pytest.approx(4 / 7)
    assert rep["by_continent_geo"]["A"]["flux_frac_outside"] == pytest.approx(400 / 500)
    assert rep["by_continent_geo"]["B"]["flux_frac_outside"] == pytest.approx(1600 / 2500)
    smeared = AOA.domain_shares(outside, area, 1.37 * rs * area, {"by_continent_geo": cont})
    assert _close(smeared, rep)                                 # a common smearing factor cancels in every share
    assert AOA.shares(np.zeros(0, bool), np.zeros(0), np.zeros(0))["area_frac_outside"] is None
    assert AOA.smearing_factor(np.log([2.0, 8.0]), np.log([1.0, 4.0])) == pytest.approx(2.0)


def _close(a: dict, b: dict) -> bool:
    """Nested dicts equal up to rounding of their floats."""
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    return a == pytest.approx(b, rel=1e-12)


def test_lat_bands_are_right_closed():
    bands = NEW_KEYS["lat_bands"]
    lat = np.array([-89.9, -60.0, -59.9, 0.0, 23.5, 23.6, 66.5, 89.9])
    assert list(AOA.lat_bands(lat, bands)) == ["Antarctic", "Antarctic", "S temperate", "Tropics", "Tropics",
                                               "N temperate", "N boreal", "Arctic"]
    with pytest.raises(ValueError, match="outside the band edges"):
        AOA.lat_bands(np.array([95.0]), bands)


def test_ice_sheets_by_continent_latitude_and_subunit(cfg, monkeypatch):
    grid = pd.DataFrame({"lon": [0.0, -50.0, -40.0, -100.0, 10.0], "lat": [-70.0, -61.0, 70.0, 60.0, 50.0],
                         "continent_geo": ["Antarctica", None, "North America", "North America", "Europe"]})
    seen = []

    def geographic_continent(c, lon, lat, su=None):
        seen.append(np.c_[lon, lat])
        return pd.DataFrame({"geo_subunit": np.where(in_box(lon, lat, GREENLAND), "Greenland", "Canada")})

    monkeypatch.setattr(AOA, "geographic_continent", geographic_continent)
    monkeypatch.setattr(AOA, "subunits", fake_subunits)
    ice, counts = AOA.ice_sheet_mask(cfg, grid, NEW_KEYS["ice_sheets"])
    assert list(ice) == [True, True, True, False, False]
    assert counts == {"continent_geo": 1, "south_of_lat": 2, "continent_geo_or_south_of_lat": 2,
                      "n_cells_looked_up": 2, "subunits": {"Greenland": 1}, "n_cells": 3}
    # looked up: only the cells still open whose continent is Greenland's (North America), not the European one
    assert len(seen) == 1 and np.array_equal(seen[0], grid[["lon", "lat"]].to_numpy()[2:4])
    for names, match in ((["Greenland", "Grenland"], "not Natural Earth map subunits"), (["Russia"], "Russia")):
        with pytest.raises(ValueError, match=match):
            AOA.ice_sheet_mask(cfg, grid, {**NEW_KEYS["ice_sheets"], "subunits": names})
    ice, counts = AOA.ice_sheet_mask(cfg, grid, {**NEW_KEYS["ice_sheets"], "subunits": []})
    assert list(ice) == [True, True, False, False, False] and counts["subunits"] == {} and len(seen) == 1


# ---------------------------------------------------------------- the stage

def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def test_stage_result(staged):
    r, d = staged.res, staged.d
    assert r["exploratory"] is True and r["method"] and r["continent_column"] == "continent_geo"
    assert set(r["_inputs"]) == {"features_analysis.json", "fetch_worldclim.json"}
    assert set(r["_outputs"]) == {"interim:aoa_di_grid.parquet", "figures:phase2/aoa_di_map.png",
                                  "figures:phase2/aoa_di_map.pdf", "figures:phase2/aoa_variants.png",
                                  "figures:phase2/aoa_variants.pdf"}
    # sites by the geographic continent (the locked column holds garbage); two outside the list, one incomplete
    assert r["sites"] == {"n_table": len(d), "n_used": len(d) - 3, "n_continent_not_listed": 2, "n_missing_values": 1,
                          "by_continent_geo": {c: n - (c == "Asia") for c, (_x, _y, n) in BOXES.items()}}
    assert d.loc[5, "continent_geo"] == "Asia"
    ts = r["training_sets"]
    assert ts["all"]["n_sites"] == len(d) - 3 and ts["Asia"]["n_sites"] == BOXES["Asia"][2] - 1
    assert ts["Asia"]["by_continent_geo"] == {"Asia": BOXES["Asia"][2] - 1}
    for t in ("all", "Asia"):
        assert ts[t]["weights"]["none"]["values"] == {c: 0.125 for c in C8}
        assert sum(ts[t]["weights"]["permutation"]["values"].values()) == pytest.approx(1.0)
        assert sum(ts[t]["cv"]["fold_sizes"]) == ts[t]["n_sites"] and ts[t]["smearing_factor"] > 1.0
    # variants: training set x threshold x weights, in config order
    keys = [(v["train"], v["threshold"], v["weights"]) for v in r["variants"]]
    assert keys == [(t, th, w) for t in ("all", "Asia") for th in ("whisker_max", "q95")
                    for w in ("permutation", "none")]
    assert r["primary_variant"] == {"train": "all", "threshold": "whisker_max", "weights": "permutation"}
    for v in r["variants"]:
        if v["threshold"] == "whisker_max":
            assert set(v["threshold_detail"]) == {"fence", "n_train_above_fence", "train_di_max"}
            assert v["threshold_value"] <= v["threshold_detail"]["fence"]
        else:
            assert v["threshold_detail"] == {} and v["train_frac_above_threshold"] == pytest.approx(0.05, abs=0.01)
    # no global flux total anywhere (F-H25)
    assert not [k for k in _walk_keys(r) if "total" in k.lower() or "pgc" in k.lower()]
    assert staged.summary["n_variants"] == 8


def test_grid_domains_and_ice_sheets(staged):
    g = fake_grid(GRID_DEG)
    r = staged.res["grid"]
    n_ant = int(g.continent_geo.eq("Antarctica").sum())
    n_south = int((g.lat < -60).sum())
    n_green = int(in_box(g.lon, g.lat, GREENLAND).sum())
    n_na = int(g.continent_geo.eq("North America").sum())
    assert r["ice_sheets"] == {"continent_geo": n_ant, "south_of_lat": n_south,
                               "continent_geo_or_south_of_lat": n_south, "n_cells_looked_up": n_na,
                               "subunits": {"Greenland": n_green}, "n_cells": n_south + n_green}
    assert r["n_cells_unassigned_continent"] == int(g.continent_geo.isna().sum())
    dom = r["domains"]
    assert dom["all_land"]["n_cells"] == len(g) and dom["excluding_ice_sheets"]["n_cells"] == len(g) - n_south - n_green
    assert dom["all_land"]["area_km2"] == pytest.approx(g.area_km2.sum())
    assert "Antarctica" in dom["all_land"]["by_continent_geo"]
    assert "Antarctica" not in dom["excluding_ice_sheets"]["by_continent_geo"]
    assert "unassigned" in dom["excluding_ice_sheets"]["by_continent_geo"]                   # the islands
    assert dom["excluding_ice_sheets"]["by_continent_geo"]["North America"]["n_cells"] == \
        dom["all_land"]["by_continent_geo"]["North America"]["n_cells"] - n_green
    # geographic_continent ran once, on the North American cells (Greenland's continent) still in the domain
    na = g.continent_geo.eq("North America").to_numpy() & (g.lat >= -60).to_numpy()
    assert len(staged.calls) == 1 and np.array_equal(staged.calls[0], g[["lon", "lat"]].to_numpy()[na])


def test_shares_follow_from_the_grid_table(staged):
    t, r = staged.table, staged.res
    area = t.area_km2.to_numpy()
    for v in r["variants"]:
        s = f"{v['train']}"
        di = t[f"di_{s}_{v['weights']}"].to_numpy()
        inside = t[f"aoa_{s}_{v['threshold']}_{v['weights']}"].to_numpy()
        assert np.array_equal(inside, di <= v["threshold_value"])
        rs = np.exp(t[f"pred_log_{s}"].to_numpy())             # the smearing factor cancels in a share
        for dom, keep in (("all_land", np.ones(len(t), bool)), ("excluding_ice_sheets", ~t.ice_sheet.to_numpy())):
            o, a, f = ~inside[keep], area[keep], (rs * area)[keep]
            assert v[dom]["area_frac_outside"] == pytest.approx(a[o].sum() / a.sum(), rel=1e-12)
            assert v[dom]["flux_frac_outside"] == pytest.approx(f[o].sum() / f.sum(), rel=1e-12)
            na = t.continent_geo.to_numpy()[keep] == "North America"
            assert v[dom]["by_continent_geo"]["North America"]["area_frac_outside"] == \
                pytest.approx(a[o & na].sum() / a[na].sum(), rel=1e-12)
            band = t.lat_band.to_numpy()[keep] == "Tropics"
            assert v[dom]["by_lat_band"]["Tropics"]["area_frac_outside"] == \
                pytest.approx(a[o & band].sum() / a[band].sum(), rel=1e-12)
    # Antarctica (much colder than any training site) is outside the primary AOA; its cells are ice sheet
    ant = t.continent_geo.eq("Antarctica").to_numpy()
    assert not t.aoa_all_whisker_max_permutation.to_numpy()[ant].any() and t.ice_sheet.to_numpy()[ant].all()


def test_transfer_check_scores_north_america_inside_and_outside(staged):
    import xgboost
    sand, r = staged.sand, staged.res["transfer_check"]
    sites, _ = AOA.prepare_sites(staged.d, "log_rs", C8, sand["phase2"]["continents"])
    asia, na = sites[sites.continent_geo == "Asia"], sites[sites.continent_geo == "North America"]
    m = xgboost.XGBRegressor(**sand["clean_test"]["locked"]["xgb"], random_state=sand["phase2"]["transfer"]["xgb_seed"])
    m.fit(asia[C8].to_numpy("float32"), asia.log_rs.to_numpy())
    p, y = m.predict(na[C8].to_numpy("float32")).astype(float), na.log_rs.to_numpy()
    assert r["train"] == "Asia" and r["test"] == "North America" and r["exploratory"] is True
    assert r["all_sites"]["n"] == len(na) == BOXES["North America"][2]
    assert r["all_sites"]["r2"] == pytest.approx(r2_score(y, p), abs=1e-12)
    assert r["all_sites"]["rmse_log"] == pytest.approx(np.sqrt(np.mean((y - p) ** 2)), abs=1e-12)
    ts = AOA.train_set(sand, "Asia", sites)
    for v in r["variants"]:
        inside = ts.spaces[v["weights"]].di(na[C8].to_numpy("float32").astype(float)) <= v["threshold_value"]
        assert v["inside"]["n"] == inside.sum() and v["outside"]["n"] == (~inside).sum()
        assert v["frac_inside"] == pytest.approx(inside.mean())
        for side, m_ in (("inside", inside), ("outside", ~inside)):
            if m_.sum() >= 2:
                assert v[side]["r2"] == pytest.approx(r2_score(y[m_], p[m_]), abs=1e-12)
                lo, hi = v[side]["ci_r2"]
                assert lo <= hi
    assert any(v["outside"]["n"] > 0 for v in r["variants"])


def test_two_runs_give_byte_identical_results(staged, monkeypatch):
    before = {k: staged.sand.from_root_key(k).read_bytes() for k in staged.res["_outputs"]}
    install_fakes(monkeypatch, staged.sand)
    AOA.aoa_sensitivity(staged.sand)
    assert staged.sand.path("results", "aoa_sensitivity.json").read_bytes() == staged.raw
    assert all(staged.sand.from_root_key(k).read_bytes() == b for k, b in before.items())


def test_row_order_of_the_features_table_does_not_matter(staged, cfg, tmp_path, monkeypatch):
    sand = sandbox(cfg, tmp_path, edit=light)
    record_features(sand, staged.d.sample(frac=1.0, random_state=3).reset_index(drop=True))
    install_fakes(monkeypatch, sand)
    AOA.aoa_sensitivity(sand)
    res = json.loads(sand.path("results", "aoa_sensitivity.json").read_bytes())
    # the features result differs (other table bytes), and so does the config hash (each sandbox has its own raw path)
    strip = lambda x: {k: v for k, v in x.items() if k not in ("_inputs", "_provenance")}   # noqa: E731
    assert strip(res) == strip(staged.res)


def test_refuses_a_stale_features_table(cfg, tmp_path, monkeypatch):
    sand = sandbox(cfg, tmp_path, edit=light)
    d = synth_sites()
    paths = record_features(sand, d)
    install_fakes(monkeypatch, sand)
    write_table(d.iloc[:-1], paths[0])                         # changed after features_analysis recorded it
    with pytest.raises(StaleInputError, match="changed after the run"):
        AOA.aoa_sensitivity(sand)
    record_features(sand, d)
    other = sandbox(cfg, tmp_path, edit=lambda x: (light(x), x["phase2"]["aoa"].__setitem__("perm_seed", 1)))
    with pytest.raises(StaleInputError, match="different config"):   # recorded under another config
        AOA.aoa_sensitivity(other)
    written = [sand.path("results", "aoa_sensitivity.json"), sand.path("interim", "aoa_di_grid.parquet"),
               sand.path("figures", "phase2", "aoa_di_map.png"), sand.path("figures", "phase2", "aoa_variants.pdf")]
    assert not any(p.exists() for p in written)


@pytest.mark.parametrize("edit,match", [
    (lambda a: a.pop("lat_bands"), "lacks"),
    (lambda a: a.__setitem__("learner", "RF"), "only 'XGB'"),
    (lambda a: a.__setitem__("weights", ["permutation", "shap"]), "unknown"),
    (lambda a: a.__setitem__("thresholds", ["whisker_max", "q90"]), "no entry"),
    (lambda a: a.__setitem__("train", ["all", "Atlantis"]), "neither"),
    (lambda a: a.__setitem__("transfer_check", {"train": "all", "test": "North America"}), "outside the training set"),
    (lambda a: a["lat_bands"].__setitem__("labels", ["one"]), "one label per interval"),
])
def test_settings_are_checked_before_anything_is_read(cfg, tmp_path, edit, match):
    sand = sandbox(cfg, tmp_path, edit=lambda x: (light(x), edit(x["phase2"]["aoa"])))
    with pytest.raises(ValueError, match=match):
        AOA.aoa_sensitivity(sand)                              # no features result exists: settings fail first
    assert not sand.path("results", "aoa_sensitivity.json").exists()


def test_figures_are_written(staged):
    for name in ("aoa_di_map", "aoa_variants"):
        png = staged.sand.path("figures", "phase2", f"{name}.png")
        pdf = staged.sand.path("figures", "phase2", f"{name}.pdf")
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and pdf.read_bytes()[:5] == b"%PDF-"


def test_r2_matches_scikit_learn():
    rng = np.random.default_rng(1)
    y, p = rng.normal(size=40), rng.normal(size=40)
    assert AOA.r2(y, p) == pytest.approx(r2_score(y, p), abs=1e-12)
    assert AOA.r2(np.ones(3), np.ones(3)) == 1.0 and AOA.r2(np.ones(3), np.zeros(3)) == 0.0
