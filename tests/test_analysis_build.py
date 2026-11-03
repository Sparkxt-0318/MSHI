"""The analysis build and its pieces (the author's decisions Q-2, Q-5, Q-6 of 2026-11-03; docs/DECISIONS.md
D-P2-1 to D-P2-4): geodesic distances, the geographic continent, the COSORE port rule, the per-group
reproduction gate and the geographic-Europe sensitivity stage. Offline; no real Europe outcome is scored."""
import copy
import json
import math

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from mshi.config import Config
from mshi.io import StaleInputError, write_result, write_table
from test_robustness import full_sandbox, sandbox


def _subunits_present(cfg) -> bool:
    from mshi.data.fetch import naturalearth_path
    f = cfg["site_build_analysis"]["geo_continent"]["subunits_file"]
    return naturalearth_path(cfg, f).exists() and naturalearth_path(cfg, "ne_50m_admin_0_countries.geojson").exists()


# ---------------------------------------------------------------- geodesic distances

def test_geodesic_km_known_cases():
    from mshi.geo import geodesic_km
    sq = box(1.0, -0.5, 2.0, 0.5)                       # 1 degree east of (0, 0) on the equator
    assert geodesic_km(0.0, 0.0, sq) == pytest.approx(111.32, abs=0.2)
    assert geodesic_km(1.5, 0.0, sq) == 0.0              # inside
    assert geodesic_km(0.0, 60.0, box(1.0, 59.5, 2.0, 60.5)) == pytest.approx(111.32 * math.cos(math.radians(60)), rel=0.01)
    across = box(-179.9, -1.0, -179.0, 1.0)              # across the antimeridian from lon 179.9
    assert geodesic_km(179.9, 0.0, across) == pytest.approx(22.26, abs=0.2)
    assert geodesic_km(0.0, 0.0, box(100.0, 0.0, 101.0, 1.0), max_km=2000.0) == math.inf     # far: inf, not a guess


def test_nearest_within_km_picks_the_geodesic_nearest():
    import geopandas as gpd
    from mshi.geo import nearest_within_km
    g = gpd.GeoSeries([box(0.5, 0, 1.0, 1), box(-1.0, 0, -0.45, 1)])
    k, km = nearest_within_km(0.0, 0.5, g, max_km=100.0)
    assert k == 1 and km == pytest.approx(0.45 * 111.32 * math.cos(math.radians(0.5)), rel=0.01)
    assert nearest_within_km(0.0, 0.5, g, max_km=10.0) == (None, math.inf)


# ---------------------------------------------------------------- geographic continent

@pytest.mark.data
def test_geographic_continent_assigns_overseas_territories_by_location(cfg):
    if not _subunits_present(cfg):
        pytest.skip("Natural Earth files not present; run `make data` first")
    from mshi.geo import geographic_continent
    pts = {"Paracou, French Guiana": (-52.92, 5.27, "South America"), "Tenerife": (-16.63, 28.29, "Africa"),
           "Hawaii": (-155.3, 19.8, "Oceania"), "Svalbard": (15.6, 78.2, "Europe"), "Madrid": (-3.7, 40.4, "Europe"),
           "Moscow": (37.6, 55.75, "Europe"), "Novosibirsk": (82.9, 55.0, "Asia"),
           "Russia west of 60E (locked split kept)": (59.0, 58.0, "Europe"),
           "Azores (open ocean: UN region)": (-25.67, 37.75, "Europe"), "Reunion (open ocean: UN region)": (55.5, -21.1, "Africa"),
           "Paris": (2.35, 48.85, "Europe"), "Sao Paulo": (-46.6, -23.5, "South America")}
    lon = [v[0] for v in pts.values()]
    lat = [v[1] for v in pts.values()]
    got = geographic_continent(cfg, lon, lat)
    assert dict(zip(pts, got.continent_geo)) == {k: v[2] for k, v in pts.items()}
    off = geographic_continent(cfg, [-9.65, -30.0], [38.7, 30.0])     # 20 km off Portugal; mid-Atlantic
    assert off.continent_geo.iloc[0] == "Europe" and 0 < off.geo_subunit_km.iloc[0] <= 50
    assert pd.isna(off.continent_geo.iloc[1])


def test_open_ocean_subunits_take_their_un_region(cfg, monkeypatch):
    import geopandas as gpd
    from mshi import geo
    fake = gpd.GeoDataFrame({"ADMIN": ["X", "Y", "Z"], "SUBUNIT": ["a", "b", "c"],
                             "CONTINENT": [geo.OPEN_OCEAN, geo.OPEN_OCEAN, "Asia"],
                             "REGION_UN": ["Americas", "Americas", "Asia"],
                             "SUBREGION": ["South America", "Caribbean", "Eastern Asia"]},
                            geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)], crs=4326)
    monkeypatch.setattr(geo.gpd, "read_file", lambda p: fake)
    monkeypatch.setattr(geo, "verify_sha256", lambda p, h: None)
    su = geo.subunits(cfg)
    assert list(su.continent_geo) == ["South America", "North America", "Asia"]


# ---------------------------------------------------------------- COSORE analysis rule

def test_parse_ports_handles_tabs_quotes_and_short_rows(tmp_path):
    from mshi.data.cosore import parse_ports
    p = tmp_path / "PORTS.txt"
    p.write_text("# PORTS.txt\n#\tcomment\nCSR_PORT,\tCSR_MSMT_VAR,\tCSR_TREATMENT,\tCSR_AREA,\tCSR_SPECIES\n"
                 "1,\t\tRs,\t\tNone,\t\t80,\t\t\"Quercus alba, Acer rubrum\"\n2,\tRh,\tTrenched\n0,\tRs,\tNone,\t,\t\n")
    ports = parse_ports(p)
    assert ports[1]["CSR_SPECIES"] == "Quercus alba, Acer rubrum" and ports[1]["CSR_TREATMENT"] == "None"
    assert ports[2] == {"CSR_PORT": "2", "CSR_MSMT_VAR": "Rh", "CSR_TREATMENT": "Trenched", "CSR_AREA": "", "CSR_SPECIES": ""}
    assert set(ports) == {0, 1, 2}


def _port_frame(port, days, flux_by_month):
    t = pd.to_datetime(days)
    secs = (t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)      # POSIX seconds, as COSORE stores them
    return pd.DataFrame({"CSR_PORT": port, "CSR_TIMESTAMP_BEGIN": secs,
                         "CSR_FLUX_CO2": [flux_by_month[d.month] for d in t]})


def test_port_rule_keeps_only_untreated_full_year_rs_ports(cfg):
    from mshi.data.cosore import port_annuals
    p = cfg["cosore_analysis"]
    factor = p["molar_mass_c"] * p["seconds_per_year"] / 1e6
    year = pd.date_range("2015-01-01", "2015-12-31", freq="D")
    summer = pd.date_range("2015-04-01", "2015-11-30", freq="D")
    flux = {m: float(m) for m in range(1, 13)}                       # 1..12 umol m-2 s-1
    uneven = year[(year.month >= 4) & (year.month <= 11)].append(year[~((year.month >= 4) & (year.month <= 11))][::4])
    df = pd.concat([_port_frame(1, year, flux), _port_frame(2, year, flux), _port_frame(3, year, flux),
                    _port_frame(4, summer, flux), _port_frame(5, uneven, flux)])
    meta = {1: {"CSR_PORT": "1", "CSR_MSMT_VAR": "Rs", "CSR_TREATMENT": "None"},
            2: {"CSR_PORT": "2", "CSR_MSMT_VAR": "Rh", "CSR_TREATMENT": "None"},
            3: {"CSR_PORT": "3", "CSR_MSMT_VAR": "Rs", "CSR_TREATMENT": "Girdled"},
            0: {"CSR_PORT": "0", "CSR_MSMT_VAR": "Rs", "CSR_TREATMENT": "None"}}      # ports 4, 5: port-0 row
    t, err = port_annuals(df, meta, p, factor)
    assert err is None
    by = t.set_index("port")
    assert list(by.kept) == [True, False, False, False, True]
    assert "CSR_MSMT_VAR Rh" in by.why_not[2] and "treated (Girdled)" in by.why_not[3] and "not full-year" in by.why_not[4]
    assert by.meta_port[4] == 0
    assert by.rs_annual[1] == pytest.approx(6.5 * factor)          # mean of the 12 monthly means
    # uneven sampling (dense in summer): the month-balanced value is still 6.5; the plain mean is pulled up
    assert by.rs_annual[5] == pytest.approx(6.5 * factor) and by.rs_annual_obs_mean[5] > 6.6 * factor


# ---------------------------------------------------------------- the geodesic coordinate check

@pytest.mark.data
def test_coordinate_check_uses_geodesic_distance(cfg):
    """Malta (F-H3): records 95-98 km from Italy are more than 100 km away in Web Mercator."""
    if not _subunits_present(cfg):
        pytest.skip("Natural Earth files not present; run `make data` first")
    from mshi.data.sites_analysis import assign_countries_geodesic, coordinate_check_geodesic, countries
    r = pd.DataFrame({"lon": [14.45, 14.45], "lat": [35.9, 35.9], "src": "srdb", "Country": ["Italy", "Spain"],
                      "rs": 800.0})
    cty = countries(cfg)
    r = coordinate_check_geodesic(cfg, assign_countries_geodesic(cfg, r, cty), cty)
    assert list(r.geo_country) == ["Malta", "Malta"]
    assert 80 < r.dist_to_reported_country_km.iloc[0] < 100 and not r.f_coord.iloc[0]
    assert r.f_coord.iloc[1] and r.dist_to_reported_country_km.iloc[1] > 100


# ---------------------------------------------------------------- the per-group reproduction gate

def test_row_groups():
    from mshi.analysis.repro_checks import row_group
    assert row_group("Locked test: Europe R²") == "locked_test"
    assert row_group("Locked test (repo-filter sensitivity): re-run identical to the locked result") == "locked_test"
    assert row_group("NPP r vs committed NPP (original 889 sites)") == "npp"
    assert row_group("Original sites with NPP missing in the committed tables but present in v3") == "npp"
    assert row_group("QC sites: Europe") == "site_build" and row_group("COSORE sites with an annual value") == "site_build"


def test_gate_opens_per_row_group(cfg, tmp_path, monkeypatch):
    """A stage built only on the site build runs when only the gridded rows are NOT RUN; one that uses
    features does not."""
    import mshi.run as R
    from mshi.run import Stage
    ran = []
    rows = ([{"quantity": f"QC sites: {i}", "status": "PASS", "group": "site_build"} for i in range(17)]
            + [{"quantity": "Locked test: Europe n", "status": "NOT RUN", "group": "locked_test"},
               {"quantity": "NPP r", "status": "NOT RUN", "group": "npp"}])
    monkeypatch.setattr(R, "_stages", lambda: [
        Stage("repro_checks", lambda c: {}),
        Stage("noise", lambda c: ran.append("noise") or {}, [], needs=("site_build",)),
        Stage("transfer", lambda c: ran.append("transfer") or {}, [])])
    sand = full_sandbox(cfg, tmp_path)
    write_result(sand, {"rows": rows, "summary": {"PASS": 17, "NOT RUN": 2}}, "reproduction_check.json")
    assert R.run(["noise", "transfer"], sand) == 2 and ran == ["noise"]
    rows[0]["status"] = "FAIL"
    write_result(sand, {"rows": rows, "summary": {"PASS": 16, "FAIL": 1, "NOT RUN": 2}}, "reproduction_check.json")
    assert R.run(["noise"], sand) == 2 and ran == ["noise"]                     # a site-build FAIL closes it


# ---------------------------------------------------------------- geographic-Europe sensitivity (Q-5)

def _synthetic_locked_features(cfg, sand, rng):
    sites = pd.read_parquet(cfg.path("derived", "sites_v3_qc.parquet"))
    d = sites[["site_id", "lat", "lon", "continent", "country"]].copy()
    cols = set().union(*map(set, cfg["clean_test"]["locked"]["sets"].values()))
    for c in sorted(cols):
        d[c] = rng.gamma(3.0, 10.0, len(d))
    d["log_rs"] = 5.5 + 0.02 * d.bio01 + 0.1 * np.log(d.bio12) + rng.normal(0, 0.3, len(d))   # synthetic target
    sand.path("interim").mkdir(parents=True, exist_ok=True)
    outs = [write_table(d, sand.path("interim", f"features_v3_{t}.parquet")) for t in cfg["clean_test"]["variants"]]
    write_result(sand, {"synthetic": True}, "features.json", outputs=outs)
    return d


@pytest.mark.data
def test_europe_geo_sensitivity_on_synthetic_features(cfg, tmp_path, monkeypatch):
    if not _subunits_present(cfg):
        pytest.skip("Natural Earth files not present; run `make data` first")
    from mshi.analysis import clean_test as CT
    from mshi.analysis import europe_geo as EG
    sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=tmp_path)   # outputs sandboxed; pinned raw kept
    d = _synthetic_locked_features(cfg, sand, np.random.default_rng(3))

    class Light(CT.LockedTest):
        def __init__(self, c, **kw):
            super().__init__(c, **kw)            # verifies the real lock
            self.L = copy.deepcopy(self.L)
            self.L["bootstrap_n"] = 40

    monkeypatch.setattr(EG, "LockedTest", Light)
    lt = Light(sand)
    train, test = d[d.continent == "Asia"], d[d.continent == "Europe"]
    a, e, _f, _m, p = lt.score(train, test, "TP", "OLS-TP")
    fake_locked = {"selected": {"set": "TP", "learner": "OLS-TP"},
                   "primary": lt.metrics(e.log_rs.values, p, e.lon.values, e.lat.values, np.full(len(e), a.log_rs.mean()))}
    real_read = EG.read_json
    monkeypatch.setattr(EG, "read_json", lambda path: fake_locked if "clean_test_europe" in str(path) else real_read(path))
    out = EG.europe_geo_sensitivity(sand)
    res = json.loads(sand.path("results", "europe_geo_sensitivity.json").read_text())
    assert res["exploratory"] is True and res["declared_post_hoc_sensitivity"] is True
    assert res["control_full_locked_set"]["max_abs_diff_vs_locked"] == 0.0
    excl = {x["site_id"]: x["continent_geo"] for x in res["excluded"]}
    assert sorted(excl.values()) == ["Africa", "Africa", "South America", "South America"]   # Canaries, French Guiana
    assert out["n"] == len(e) - 4 and res["geographic_europe"]["n"] == out["n"]
    assert set(res["vs_author_reference"]) == {"n_equal", "r2_diff", "ci_site_diff", "matches"}
    assert res["_inputs"].keys() == {"features.json"}

    fake_locked["primary"] = {**fake_locked["primary"], "r2": fake_locked["primary"]["r2"] + 0.01}
    sand.path("results", "europe_geo_sensitivity.json").unlink()
    with pytest.raises(EG.ControlMismatch):                       # control fails: nothing is written
        EG.europe_geo_sensitivity(sand)
    assert not sand.path("results", "europe_geo_sensitivity.json").exists()


def test_europe_geo_sensitivity_refuses_stale_features(cfg, tmp_path):
    from mshi.analysis.europe_geo import europe_geo_sensitivity
    sand = sandbox(cfg, tmp_path)
    write_result(sand, {"synthetic": True}, "features.json")       # records no feature tables
    with pytest.raises(StaleInputError, match="not an output recorded"):
        europe_geo_sensitivity(sand)


# ---------------------------------------------------------------- features for the analysis tables

def _wgs_raster(path, values, dtype="float32"):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


def test_features_analysis_attaches_the_same_features(cfg, tmp_path, monkeypatch):
    from mshi.data import features as F
    from mshi.data.modis import modis_cache_key, site_key, write_modis_cache
    sand = sandbox(cfg, tmp_path)
    st = pd.DataFrame({"site_id": ["a1", "a2", "a3"], "lat": [45.2, -10.4, 60.1], "lon": [10.3, -60.2, 100.7],
                       "log_rs": 6.0, "continent": ["Europe", "South America", "Asia"],
                       "continent_geo": ["Europe", "South America", "Asia"]})
    tabs = [write_table(st, sand.path("derived", f"sites_analysis_{t}.parquet")) for t in ("qc", "repo")]
    tabs.insert(0, write_table(st.assign(rec_id=st.site_id), sand.path("derived", "records_analysis.parquet")))
    write_result(sand, {"fake": True}, "build_sites_analysis.json", outputs=tabs)
    rdir = sand.path("interim", "rasters")
    rdir.mkdir(parents=True)
    paths = {}
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    for i in range(1, cfg["features"]["worldclim_vars"] + 1):
        _wgs_raster(rdir / f"wc{i}.tif", 20 - 0.3 * np.abs(lat) + i)
        paths[("wc", i)] = rdir / f"wc{i}.tif"
    for v in cfg["sources"]["soilgrids"]["variables"]:
        _wgs_raster(rdir / f"{v}.tif", 100 + 0 * lat, dtype="int16")
        paths[("sg", v)] = rdir / f"{v}.tif"
    monkeypatch.setattr(F, "worldclim_path", lambda c, i: paths[("wc", i)])
    monkeypatch.setattr(F, "soilgrids_path", lambda c, v: paths[("sg", v)])
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json",
                 outputs=[paths[("wc", i)] for i in range(1, cfg["features"]["worldclim_vars"] + 1)])
    write_result(sand, {"synthetic": True}, "fetch_soilgrids.json",
                 outputs=[paths[("sg", v)] for v in cfg["sources"]["soilgrids"]["variables"]])
    keys = site_key(st.lat, st.lon).values
    mod = pd.DataFrame({"site_key": keys, "npp": [400.0, 900.0, 300.0], "npp_n": 5, "lst_day": [20.0, 30.0, 5.0],
                        "lst_night": [8.0, 22.0, -10.0]})
    out = write_modis_cache(sand, mod, modis_cache_key(sand, keys), {"n_failed_reads": 0})
    write_result(sand, {"n_failed_reads": 0}, "modis_points.json", outputs=[out])
    F.features_analysis(sand)
    d = pd.read_parquet(sand.path("interim", "features_analysis_qc.parquet"))
    assert list(d.site_id) == ["a1", "a2", "a3"] and (d.continent_geo == st.continent_geo).all()
    assert d[["bio01", "bio12", "clay", "npp", "lst_diurnal_range"]].notna().all().all()
    assert d.lst_diurnal_range.tolist() == [12.0, 8.0, 15.0]
    res = json.loads(sand.path("results", "features_analysis.json").read_text())
    assert res["exploratory"] is True and set(res["_inputs"]) == {"build_sites_analysis.json", "modis_points.json",
                                                                 "fetch_worldclim.json", "fetch_soilgrids.json"}
    write_table(st.assign(log_rs=7.0), tabs[1])                        # an analysis table replaced
    with pytest.raises(StaleInputError, match="sites_analysis_qc.parquet changed after the run"):
        F.features_analysis(sand)
