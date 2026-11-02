"""End-to-end sandbox helpers: non-smoke Config with absolute scratch paths, fakes for the blocked sources only.

Fakes (nothing else is replaced):
- mshi.data.rasters.download     -> writes a synthetic WorldClim zip (19 GeoTIFFs) / one synthetic SoilGrids GeoTIFF
- mshi.data.fetch.download       -> wrapper around the REAL download (records whether it downloaded)
- mshi.netutil.check_reachable   -> recorder (Planetary Computer hosts are blocked by policy)
- pystac_client.Client.open      -> FakeCatalog (complete 2020-2024 catalog, Terra + Aqua items)
- mshi.data.modis.TokenCache     -> FakeTokens
- mshi.data.modis.read_windows   -> deterministic synthetic window means (stable hash of href + site_key)
- mshi.analysis.clean_test.LockedTest -> Light: real lock verified, fewer trees/bootstraps, SYNTHETIC target
- requests.sessions.Session.send -> network guard: records and refuses every request
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sys
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REPO = Path("/home/user/MSHI")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SCR = Path(__file__).resolve().parents[1]
FIX = SCR / "fixtures"

STATE = {"raster_downloads": [], "fetch_downloads": [], "reachable": [], "searches": 0, "reads": 0,
         "net_attempts": [], "token_gets": 0, "light_runs": 0}
_LOCK = threading.Lock()


def reset_state():
    for k, v in STATE.items():
        STATE[k] = [] if isinstance(v, list) else 0


def make_cfg(sb: Path, edit=None):
    from mshi.config import Config, load_config
    base = load_config()
    data = copy.deepcopy(base.data)
    for root in ("raw", "interim", "derived", "results", "figures"):
        data["paths"][root] = str(Path(sb) / root)
    if edit:
        edit(data)
    return Config(data, source=base.source)      # out_root None: NOT a smoke run


# ------------------------------------------------------------------ synthetic rasters

def _gtiff_bytes(values: np.ndarray, west: float, north: float, res: float, dtype: str, nodata=None) -> bytes:
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    prof = dict(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype=dtype,
                crs="EPSG:4326", transform=from_origin(west, north, res, res))
    if nodata is not None:
        prof["nodata"] = nodata
    with MemoryFile() as mf:
        with mf.open(**prof) as dst:
            dst.write(values.astype(dtype), 1)
        return bytes(mf.read())


def worldclim_zip(cfg, variant: str = "1") -> Path:
    """Deterministic zip of 19 synthetic 1-degree bio layers named as in sources.worldclim.file_pattern.
    variant "2" stands for an upstream re-release (other bytes and values; WorldClim publishes no checksum)."""
    out = FIX / ("wc2.1_2.5m_bio.zip" if variant == "1" else f"wc2.1_2.5m_bio_v{variant}.zip")
    if out.exists():
        return out
    FIX.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7 if variant == "1" else 70 + int(variant))
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    pat = "wc2.1_2.5m_bio_{i}.tif"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i in range(1, 20):
            if i == 12:
                v = 200 + 2500 * np.cos(np.radians(lat)) ** 2 + 300 * np.sin(np.radians(3 * lon)) ** 2
            elif i == 1:
                v = 28 - 0.45 * np.abs(lat) + 2 * np.sin(np.radians(lon))
            else:
                v = 10 + i * 3 + 15 * np.cos(np.radians(lat + 7 * i)) + 4 * np.sin(np.radians(lon * (i % 5 + 1)))
            v = v + rng.normal(0, 0.5, v.shape)
            v[np.abs(lat) > 86] = -3.4e38                    # WorldClim-like nodata (below -1e30)
            zi = zipfile.ZipInfo(pat.format(i=i), date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, _gtiff_bytes(v, -180, 90, 1.0, "float32", nodata=-3.4e38))
    out.write_bytes(buf.getvalue())
    return out


_SG_CACHE: dict = {}


def soilgrids_tiff(coverage_id: str) -> bytes:
    """Deterministic synthetic SoilGrids GeoTIFF (int16, 1 degree, lon -180..180, lat -56..83) per coverage id."""
    if coverage_id not in _SG_CACHE:
        seed = int(hashlib.sha256(coverage_id.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        lat = np.linspace(82.5, -55.5, 139)[:, None] * np.ones((1, 360))
        lon = np.ones((139, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
        base = 150 + 80 * np.cos(np.radians(lat)) ** 2 + 40 * np.sin(np.radians(2 * lon)) + rng.normal(0, 5, lat.shape)
        base = np.clip(base, 1, None)
        base[rng.random(lat.shape) < 0.01] = 0          # zeros = missing (zero_is_missing)
        _SG_CACHE[coverage_id] = _gtiff_bytes(base, -180, 83, 1.0, "int16")
    return _SG_CACHE[coverage_id]


def fake_raster_download(url, dest, sha256=None, retries=4, timeout=600, session=None, params=None,
                         reuse_existing=False, sleep=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if params and "COVERAGEID" in params:
        body = soilgrids_tiff(params["COVERAGEID"])
        what = params["COVERAGEID"]
    else:
        variant = os.environ.get("E2E_WC_VARIANT", "1")
        body = worldclim_zip(None, variant).read_bytes() if variant != "1" else (FIX / "wc2.1_2.5m_bio.zip").read_bytes()
        what = url + ("" if variant == "1" else f" (variant {variant})")
    digest = hashlib.sha256(body).hexdigest()
    if sha256 and digest != sha256:
        from mshi.netutil import ChecksumMismatchError
        raise ChecksumMismatchError(f"{url}: SHA-256 {digest} != pinned {sha256}; nothing written to {dest}")
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(body)
    tmp.replace(dest)
    with _LOCK:
        STATE["raster_downloads"].append(what)
    return {"path": str(dest), "sha256": digest, "downloaded": True}


# ------------------------------------------------------------------ MODIS fakes

def _item(iid, start: datetime, end: datetime, assets, dt_none: bool):
    return SimpleNamespace(id=iid, datetime=None if dt_none else start,
                           properties={"start_datetime": start.isoformat().replace("+00:00", "Z"),
                                       "end_datetime": end.isoformat().replace("+00:00", "Z")},
                           assets={a: SimpleNamespace(href=f"https://modiseuwest.blob.core.windows.net/modis-061-cogs/"
                                                           f"{iid}/{a}.tif") for a in assets})


class FakeCatalog:
    """Complete 2020-2024 catalog for any tile: annual NPP (Terra + Aqua) and every 8-day LST composite
    (Terra + Aqua: 2 x 46 x 5 = 460 items per tile, below max_items_per_tile = 500)."""

    def __init__(self, years=range(2020, 2025)):
        self.years = list(years)

    def search(self, collections, datetime=None, query=None, max_items=None, **kw):  # noqa: A002
        with _LOCK:
            STATE["searches"] += 1
        h = query["modis:horizontal-tile"]["eq"]
        v = query["modis:vertical-tile"]["eq"]
        tile = f"h{h:02d}v{v:02d}"
        its = []
        col = collections[0]
        for y in self.years:
            if col == "modis-17A3HGF-061":
                for plat in ("MOD17A3HGF", "MYD17A3HGF"):
                    s = _dt(y, 1, 1)
                    its.append(_item(f"{plat}.A{y}001.{tile}.061", s, _dt(y, 12, 31), ["Npp_500m"], dt_none=True))
            elif col == "modis-11A2-061":
                for plat in ("MOD11A2", "MYD11A2"):
                    for doy in range(1, 366, 8):
                        s = _dt(y, 1, 1) + timedelta(days=doy - 1)
                        its.append(_item(f"{plat}.A{y}{doy:03d}.{tile}.061", s, s + timedelta(days=7),
                                         ["LST_Day_1km", "LST_Night_1km"], dt_none=(doy % 16 == 1)))
            else:
                raise ValueError(col)
        for gap in filter(None, os.environ.get("E2E_DROP", "").split(";")):
            gtile, gkind, gper = gap.split()
            if gtile != tile:
                continue
            if gkind == "npp" and col == "modis-17A3HGF-061":
                its = [i for i in its if f".A{gper}" not in i.id]
            if gkind == "lst" and col == "modis-11A2-061":
                y, mo = map(int, gper.split("-"))
                its = [i for i in its if not (_start(i).year == y and _start(i).month == mo)]
        its = its[: max_items] if max_items else its
        its = list(reversed(its))           # an API order that is not the sort order
        return SimpleNamespace(item_collection=lambda: its)


def _start(i):
    return pd.Timestamp(i.properties["start_datetime"]).to_pydatetime()


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


class FakeTokens:
    def __init__(self, *a, **k):
        pass

    def get(self, force=False):
        with _LOCK:
            STATE["token_gets"] += 1
        return "sv=fake&sig=fake"


def _u(*parts) -> float:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:12], 16) / float(1 << 48)


def fake_read_windows(href, sub, kind, m):
    assert "?sv=fake" in href, href
    base = href.split("?")[0]
    out = {}
    for k in sub.site_key:
        if _u("nan", k) < 0.02:                 # ~2% of sites: no valid pixel in any raster
            out[k] = np.nan
            continue
        u = _u(base, k)
        if kind == "npp":
            out[k] = 200.0 + 900.0 * _u("site", k) + 60.0 * (u - 0.5)
        elif kind == "lst_day":
            out[k] = 5.0 + 25.0 * _u("site", k) + 4.0 * (u - 0.5)
        else:
            out[k] = -8.0 + 18.0 * _u("site", k) + 4.0 * (u - 0.5)
    with _LOCK:
        STATE["reads"] += 1
    return out


# ------------------------------------------------------------------ install

def install(monkey: dict | None = None):
    """Install every fake (idempotent)."""
    import pystac_client
    import requests

    from mshi.analysis import clean_test as CT
    from mshi.data import fetch as F
    from mshi.data import modis as M
    from mshi.data import rasters as R
    import mshi.netutil as NU

    worldclim_zip(make_cfg(SCR / "unused"))
    R.download = fake_raster_download

    real_download = NU.download

    def rec_download(url, dest, *a, **k):
        r = real_download(url, dest, *a, **k)
        STATE["fetch_downloads"].append((url.rsplit("/", 1)[-1], r["downloaded"]))
        return r
    F.download = rec_download

    def rec_reachable(url, timeout=30, require_ok=True):
        STATE["reachable"].append(url)
    NU.check_reachable = rec_reachable

    pystac_client.Client.open = staticmethod(lambda url, *a, **k: FakeCatalog())
    M.TokenCache = FakeTokens
    M.read_windows = fake_read_windows

    def guard(self, request, **kw):
        STATE["net_attempts"].append(request.url)
        raise requests.exceptions.ConnectionError(f"e2e network guard: refused {request.url}")
    requests.sessions.Session.send = guard

    base = getattr(CT, "_E2E_REAL_LockedTest", CT.LockedTest)
    CT._E2E_REAL_LockedTest = base

    class Light(base):
        def __init__(self, c, **kw):
            super().__init__(c, **kw)            # verifies the real lock (require_lock=True by default)
            self.L = copy.deepcopy(self.L)
            self.L["rf"]["n_estimators"] = self.L["xgb"]["n_estimators"] = 15
            self.L["bootstrap_n"], self.L["seed_spread"] = 30, [0, 1]
            self.L["aoa_perm_repeats"] = 2

        def run(self, d, score=True):
            STATE["light_runs"] += 1
            d = d.copy()
            rng = np.random.default_rng(20261102)
            # SYNTHETIC target: the real log_rs is overwritten before anything is fitted or scored
            d[self.T] = (4.6 + 0.025 * d.bio01 + 0.12 * np.log(d.bio12) + 0.0004 * d.npp.fillna(600)
                         + 0.002 * d.soc.fillna(15) + rng.normal(0, 0.35, len(d)))
            return super().run(d, score)

    CT.LockedTest = Light
    return Light


# ------------------------------------------------------------------ inspection helpers

def result_files(cfg):
    return sorted(p for p in cfg.path("results").glob("*.json"))


def staleness_report(cfg) -> dict:
    from mshi.io import result_staleness
    out = {}
    for p in result_files(cfg):
        obj = json.loads(p.read_text())
        out[p.name] = result_staleness(cfg, obj) if "_provenance" in obj else "(no _provenance: " + p.name + ")"
    return out


def tree_hashes(root: Path) -> dict:
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def last_log(cfg, n_stages: int | None = None) -> list[dict]:
    lines = cfg.path("results", "run_log.jsonl").read_text().splitlines()
    recs = [json.loads(x) for x in lines]
    return recs[-n_stages:] if n_stages else recs
