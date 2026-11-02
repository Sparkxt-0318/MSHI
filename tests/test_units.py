"""Unit tests on small synthetic inputs (code paths only; no scientific result is produced here)."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import r2_score

from mshi.data import cosore as cos
from mshi.data import modis
from mshi.spatial import block_folds, bootstrap_ci, cluster_within_km


# --- verbatim copies of the handoff prototype (docs/handoff/scripts/clean_test.py), for equivalence
def _folds_handoff(df, seed, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); rng = np.random.default_rng(seed); rng.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]


def _boot_ci_handoff(y, p, lon=None, lat=None, deg=None, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    if deg is None:
        bs = [r2_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    else:
        b = (np.floor(lon / deg).astype(int).astype(str) + "_" + np.floor(lat / deg).astype(int).astype(str))
        u = np.unique(b); idx = {k: np.where(b == k)[0] for k in u}; bs = []
        for _ in range(n):
            i = np.concatenate([idx[k] for k in rng.choice(u, len(u))]); bs.append(r2_score(y[i], p[i]))
    return [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]


@pytest.fixture
def pts():
    rng = np.random.default_rng(1)
    n = 400
    return pd.DataFrame({"lon": rng.uniform(-30, 160, n), "lat": rng.uniform(-40, 70, n)})


@pytest.mark.parametrize("seed", [42, 43, 44, 0])
def test_block_folds_match_handoff(pts, seed):
    ours = list(block_folds(pts.lon.values, pts.lat.values, seed, 5.0, 5))
    theirs = list(_folds_handoff(pts, seed))
    assert len(ours) == len(theirs) == 5
    for (a, b), (c, d) in zip(ours, theirs):
        assert np.array_equal(a, c) and np.array_equal(b, d)


def test_bootstrap_matches_handoff(pts):
    rng = np.random.default_rng(3)
    y = rng.normal(size=len(pts)); p = y * 0.4 + rng.normal(size=len(pts))
    assert bootstrap_ci(y, p, n=300, seed=42) == _boot_ci_handoff(y, p, n=300, seed=42)
    assert (bootstrap_ci(y, p, n=300, seed=42, lon=pts.lon.values, lat=pts.lat.values, deg=2.0)
            == _boot_ci_handoff(y, p, pts.lon.values, pts.lat.values, 2.0, n=300, seed=42))


def test_cluster_chains_and_separates():
    # 4 km steps along a meridian (~0.036 deg): a, b, c chain into one site (a-c ~8 km); d is 20 km further
    dlat = 4.0 / 111.195
    lat = np.array([50.0, 50.0 + dlat, 50.0 + 2 * dlat, 50.0 + 2 * dlat + 0.18])
    lab = cluster_within_km(lat, np.full(4, 10.0), 5.0)
    assert lab[0] == lab[1] == lab[2] and lab[3] != lab[0]


def test_cosore_factor_and_coverage_rule():
    factor = 12.011 * 31536000 / 1e6
    assert factor == pytest.approx(378.78, abs=0.01)
    t0 = pd.Timestamp("2015-01-01").value / 1e9
    day = 86400.0
    good = pd.DataFrame({"CSR_PORT": 1, "CSR_TIMESTAMP_BEGIN": t0 + np.r_[np.arange(149), 180] * day,
                         "CSR_FLUX_CO2": np.r_[np.full(149, 2.0), 100.0]})        # 150 days, span 180; one value clipped
    short = pd.DataFrame({"CSR_PORT": 2, "CSR_TIMESTAMP_BEGIN": t0 + np.arange(149) * 2 * day, "CSR_FLUX_CO2": 3.0})
    narrow = pd.DataFrame({"CSR_PORT": 3, "CSR_TIMESTAMP_BEGIN": t0 + np.arange(170) * day, "CSR_FLUX_CO2": 3.0})
    ports, err = cos.integrate_ports(pd.concat([good, short, narrow]), 150, 180, (-2.0, 50.0), factor)
    assert err is None and list(ports.port) == [1]
    expect = (149 * 2.0 + 50.0) / 150 * factor
    assert ports.rs_annual.iat[0] == pytest.approx(expect)
    none, err = cos.integrate_ports(short, 150, 180, (-2.0, 50.0), factor)
    assert none is None and err.startswith("no port")
    none, err = cos.integrate_ports(good.drop(columns="CSR_PORT"), 150, 180, (-2.0, 50.0), factor)
    assert none is None and "missing columns" in err


def test_parse_description(tmp_path):
    f = tmp_path / "DESCRIPTION.txt"
    f.write_text("# comment\nCSR_LATITUDE: 45.5\nCSR_LONGITUDE: -84.7\nCSR_IGBP: Mixed forests\nbad line\n")
    d = cos.parse_description(f)
    assert d == {"CSR_LATITUDE": "45.5", "CSR_LONGITUDE": "-84.7", "CSR_IGBP": "Mixed forests"}


# --------------------------------------------------------------------- MODIS

def test_modis_scaling(cfg):
    m = cfg["sources"]["modis"]
    a = np.array([-1, 0, 5000, 32700, 32761, 65535], float)
    npp = modis.scale_values(a, "npp", m)
    assert np.isnan(npp[0]) and npp[1] == 0 and npp[2] == pytest.approx(500.0) and npp[3] == pytest.approx(3270.0)
    assert np.isnan(npp[4]) and np.isnan(npp[5])
    lst = modis.scale_values(np.array([0, 14000, 15000], float), "lst", m)
    assert np.isnan(lst[0]) and lst[1] == pytest.approx(14000 * 0.02 - 273.15) and lst[2] == pytest.approx(26.85)


def test_sinusoidal_tiles(cfg):
    m = cfg["sources"]["modis"]
    h, v = modis.sinusoidal_tiles(np.array([0.5, -0.5, 116.4, -76.5]), np.array([5.0, -5.0, 39.9, 42.4]), m)
    assert list(h) == [18, 17, 26, 12] and list(v) == [8, 9, 5, 4]   # Beijing h26v05, Ithaca h12v04


def _sinu_raster(path, m, x0, y0, nx, ny, res, value_fn):
    import rasterio
    from rasterio.transform import from_origin
    arr = np.fromfunction(value_fn, (ny, nx)).astype("int16")
    with rasterio.open(path, "w", driver="GTiff", width=nx, height=ny, count=1, dtype="int16",
                       crs=m["sinusoidal_proj"], transform=from_origin(x0, y0, res, res)) as dst:
        dst.write(arr, 1)


def test_read_windows_mean_and_edge_quirk(cfg, tmp_path):
    from pyproj import Transformer
    m = cfg["sources"]["modis"]
    tf = Transformer.from_crs("EPSG:4326", m["sinusoidal_proj"], always_xy=True)
    x, y = tf.transform(10.0, 45.0)
    res = 463.3127
    x0, y0 = x - 100 * res, y + 100 * res
    f = tmp_path / "npp.tif"
    _sinu_raster(f, m, x0, y0, 200, 200, res, lambda r, c: np.full_like(r, 4000))     # NPP 400 g C everywhere
    sub = pd.DataFrame({"site_key": ["mid"], "lat": [45.0], "lon": [10.0]})
    assert modis.read_windows(str(f), sub, "npp", m)["mid"] == pytest.approx(400.0)
    # a point on the raster's west edge: half of the window lies outside and is filled with 0, which is
    # a VALID NPP value, so the mean is pulled toward 0 (handoff quirk kept for reproduction; DECISIONS.md)
    lon_edge, lat_edge = Transformer.from_crs(m["sinusoidal_proj"], "EPSG:4326", always_xy=True).transform(x0, y)
    sub = pd.DataFrame({"site_key": ["edge"], "lat": [lat_edge], "lon": [lon_edge]})
    v = modis.read_windows(str(f), sub, "npp", m)["edge"]
    assert 150 < v < 260


def test_token_cache_refresh():
    calls = []

    class R:
        def __init__(self, i): self.i = i
        def raise_for_status(self): pass
        def json(self): return {"token": f"tok{self.i}"}

    class S:
        def get(self, url, timeout):
            calls.append(url); return R(len(calls))

    tc = modis.TokenCache("u", refresh_s=1000, session=S())
    assert tc.get() == "tok1" and tc.get() == "tok1" and len(calls) == 1
    assert tc.get(force=True) == "tok2" and len(calls) == 2
    tc.refresh_s = -1
    assert tc.get() == "tok3"


def test_site_key_rounding():
    k = modis.site_key([45.123456789, -0.5], [10.0, 120.000004])
    assert list(k) == ["45.12346_10.0", "-0.5_120.0"]


# ------------------------------------------------------------------ features

def _wgs_raster(path, values, dtype="float32", nodata=None):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(0, 50, 1, 1), nodata=nodata) as dst:
        dst.write(values.astype(dtype), 1)


def test_attach_features(cfg, tmp_path, monkeypatch):
    from mshi.data import features as F
    wc = {}
    for i in range(1, 20):
        a = np.full((10, 10), float(i))
        a[0, 0] = -3.4e38                                  # WorldClim fill below -1e30 -> NaN
        _wgs_raster(tmp_path / f"wc{i}.tif", a)
        wc[i] = tmp_path / f"wc{i}.tif"
    sg = {}
    for k in cfg["sources"]["soilgrids"]["variables"]:
        a = np.full((10, 10), 200.0)
        a[0, 1] = 0                                         # 0 -> NaN (handoff: values <= 0 missing)
        _wgs_raster(tmp_path / f"{k}.tif", a, dtype="int16")
        sg[k] = tmp_path / f"{k}.tif"
    monkeypatch.setattr(F, "worldclim_path", lambda c, i: wc[i])
    monkeypatch.setattr(F, "soilgrids_path", lambda c, v: sg[v])
    sites = pd.DataFrame({"site_id": ["a", "b", "c"], "lat": [49.5, 49.5, 45.25], "lon": [0.5, 1.5, 5.75]})
    mod = pd.DataFrame({"site_key": modis.site_key([45.25], [5.75]), "npp": [500.0], "npp_n": [5],
                        "lst_day": [20.0], "lst_night": [8.0]})
    d = F.attach_features(cfg, sites, mod)
    assert np.isnan(d.bio01.iat[0]) and d.bio01.iat[2] == 1 and d.bio19.iat[2] == 19
    assert d.clay.iat[0] == pytest.approx(20.0) and np.isnan(d.clay.iat[1]) and d.bdod.iat[2] == pytest.approx(2.0)
    assert d.npp.iat[2] == 500 and np.isnan(d.npp.iat[0]) and d.lst_diurnal_range.iat[2] == pytest.approx(12.0)
