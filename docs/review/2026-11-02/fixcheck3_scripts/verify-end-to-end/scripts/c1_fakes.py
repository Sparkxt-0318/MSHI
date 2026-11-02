"""Fakes for the blocked sources only (written for this verification; independent of the reviewer's e2e_lib).

- mshi.data.rasters.download  -> synthetic WorldClim zip (19 GeoTIFFs, 1 deg) / SoilGrids GeoTIFF (int16, 1 deg)
                                 WC_VARIANT env var: "1" first release, "2" a re-release (other bytes and values)
- mshi.netutil.check_reachable -> no-op (Planetary Computer hosts are blocked by policy)
- pystac_client.Client.open   -> complete fake catalog 2020-2024 (Terra items only)
- mshi.data.modis.TokenCache  -> fake tokens; mshi.data.modis.read_windows -> deterministic synthetic window means
- mshi.analysis.clean_test.LockedTest -> lock verified for real; lighter learners; SYNTHETIC target (real log_rs
                                 is overwritten before anything is fitted or scored)
- requests Session.send       -> refuses every request (network guard)
"""
from __future__ import annotations

import copy
import hashlib
import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

COUNTS = {"wc_downloads": 0, "sg_downloads": 0, "reads": 0, "light_runs": 0}


def _gtiff(values, west, north, res, dtype, nodata=None) -> bytes:
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


def worldclim_zip_bytes(variant: str) -> bytes:
    rng = np.random.default_rng(11 if variant == "1" else 1000 + int(variant))
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i in range(1, 20):
            if i == 1:
                v = 26 - 0.42 * np.abs(lat) + 1.5 * np.cos(np.radians(2 * lon))
            elif i == 12:
                v = 250 + 2200 * np.cos(np.radians(lat)) ** 2 + 250 * np.sin(np.radians(2 * lon)) ** 2
            else:
                v = 5 + 2 * i + 12 * np.cos(np.radians(lat + 5 * i)) + 3 * np.sin(np.radians(lon * (i % 4 + 1)))
            v = v + rng.normal(0, 0.8, v.shape)
            v[np.abs(lat) > 85] = -3.4e38
            zi = zipfile.ZipInfo(f"wc2.1_2.5m_bio_{i}.tif", date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, _gtiff(v, -180, 90, 1.0, "float32", nodata=-3.4e38))
    return buf.getvalue()


def soilgrids_bytes(cov: str) -> bytes:
    rng = np.random.default_rng(int(hashlib.sha256(cov.encode()).hexdigest()[:8], 16))
    lat = np.linspace(82.5, -55.5, 139)[:, None] * np.ones((1, 360))
    lon = np.ones((139, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    v = 140 + 70 * np.cos(np.radians(lat)) ** 2 + 30 * np.sin(np.radians(3 * lon)) + rng.normal(0, 4, lat.shape)
    return _gtiff(np.clip(v, 1, None), -180, 83, 1.0, "int16")


def fake_download(url, dest, sha256=None, retries=4, timeout=600, session=None, params=None,
                  reuse_existing=False, sleep=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if params and "COVERAGEID" in params:
        body = soilgrids_bytes(params["COVERAGEID"])
        COUNTS["sg_downloads"] += 1
    else:
        body = worldclim_zip_bytes(os.environ.get("WC_VARIANT", "1"))
        COUNTS["wc_downloads"] += 1
    digest = hashlib.sha256(body).hexdigest()
    if sha256 and digest != sha256:
        from mshi.netutil import ChecksumMismatchError
        raise ChecksumMismatchError(f"{url}: SHA-256 {digest} != pinned {sha256}")
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(body)
    tmp.replace(dest)
    return {"path": str(dest), "sha256": digest, "downloaded": True}


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def _item(iid, start, assets):
    return SimpleNamespace(id=iid, datetime=start, properties={"start_datetime": start.isoformat()},
                           assets={a: SimpleNamespace(href=f"https://fake.blob.invalid/{iid}/{a}.tif") for a in assets})


class FakeCatalog:
    def search(self, collections, datetime=None, query=None, max_items=None, **kw):  # noqa: A002
        h, v = query["modis:horizontal-tile"]["eq"], query["modis:vertical-tile"]["eq"]
        tile = f"h{h:02d}v{v:02d}"
        its = []
        for y in range(2020, 2025):
            if collections[0] == "modis-17A3HGF-061":
                its.append(_item(f"MOD17A3HGF.A{y}001.{tile}.061", _dt(y, 1, 1), ["Npp_500m"]))
            else:
                for doy in range(1, 366, 8):
                    its.append(_item(f"MOD11A2.A{y}{doy:03d}.{tile}.061", _dt(y, 1, 1) + timedelta(days=doy - 1),
                                     ["LST_Day_1km", "LST_Night_1km"]))
        return SimpleNamespace(item_collection=lambda: its)


class FakeTokens:
    def __init__(self, *a, **k):
        pass

    def get(self, force=False):
        return "sv=fake"


def _u(*parts) -> float:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16) / float(1 << 48)


def fake_read_windows(href, sub, kind, m):
    base = href.split("?")[0]
    out = {}
    for k in sub.site_key:
        u = _u(base, k)
        if kind == "npp":
            out[k] = 250.0 + 800.0 * _u("s", k) + 50.0 * (u - 0.5)
        elif kind == "lst_day":
            out[k] = 6.0 + 22.0 * _u("s", k) + 3.0 * (u - 0.5)
        else:
            out[k] = -6.0 + 15.0 * _u("s", k) + 3.0 * (u - 0.5)
    COUNTS["reads"] += 1
    return out


def install():
    import pystac_client
    import requests

    import mshi.netutil as NU
    from mshi.analysis import clean_test as CT
    from mshi.data import modis as M
    from mshi.data import rasters as RA

    def guard(self, request, **kw):
        raise requests.exceptions.ConnectionError(f"network guard: refused {request.url}")
    requests.sessions.Session.send = guard
    RA.download = fake_download
    NU.check_reachable = lambda url, timeout=30, require_ok=True: None
    pystac_client.Client.open = staticmethod(lambda url, *a, **k: FakeCatalog())
    M.TokenCache = FakeTokens
    M.read_windows = fake_read_windows

    real = CT.LockedTest

    class Light(real):
        def __init__(self, c, **kw):
            super().__init__(c, **kw)                    # verifies the real lock
            self.L = copy.deepcopy(self.L)
            self.L["rf"]["n_estimators"] = self.L["xgb"]["n_estimators"] = 12
            self.L["bootstrap_n"], self.L["seed_spread"], self.L["aoa_perm_repeats"] = 40, [0, 1], 2

        def run(self, d, score=True):
            COUNTS["light_runs"] += 1
            d = d.copy()
            rng = np.random.default_rng(424242)
            # SYNTHETIC target, a function of the synthetic features; the real log_rs is never used
            d[self.T] = (4.4 + 0.03 * d.bio01 + 0.1 * np.log(d.bio12) + 0.0003 * d.npp.fillna(600)
                         + rng.normal(0, 0.3, len(d)))
            return super().run(d, score)
    CT.LockedTest = Light
