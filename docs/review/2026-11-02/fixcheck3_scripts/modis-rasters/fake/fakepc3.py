"""Fake Planetary Computer for the modis-rasters re-check (own copy, derived from
docs/review/2026-11-02/fixcheck_scripts/fidelity/modis/fakepc.py and verify-fidelity2/fake/fakepc2.py).

Catalog model (per tile, both collections hold Terra AND Aqua items, as on Planetary Computer):
- NPP (modis-17A3HGF-061): MOD17A3HGF / MYD17A3HGF annual items 2014-2025, start = Jan 1 00:00:00Z,
  end = Dec 31 23:59:59Z; Terra items of even years have datetime None (start/end_datetime only).
- LST (modis-11A2-061): MOD11A2 / MYD11A2 8-day composites 2014-2025 starting DOY 1, 9, ..., 361.
  end_mode "clip": the last composite of a year ends Dec 31 23:59:59Z; "overlap": every composite ends
  start + 8 d - 1 s, so the DOY-361 composite of year Y overlaps Jan of Y+1 (the December-2019 case).
  Terra items whose DOY % 5 == 0 have datetime None.
- search(): STAC semantics: the datetime string is expanded exactly as pystac_client 0.9.1 does
  (ItemSearch._format_datetime), and an item matches if [start, end] intersects the query interval;
  results come back in a configurable 'API order' and are truncated to max_items (pystac_client).
Rasters: small synthetic sinusoidal GeoTIFFs around the tile's points, clipped to the tile bounds (so the
boundless-read edge quirk is exercised), only for Terra items (reading an Aqua href would fail loudly).
Files are named '<href>?tok' so that href + '?' + 'tok' opens them locally.
"""
import hashlib
import os
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
from pystac_client.item_search import ItemSearch as _ItemSearch   # real class, imported before any fake module

UTC = timezone.utc
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
R_EARTH, T_TILE, X0, Y0 = 6371007.181, 1111950.5197, -20015109.354, 10007554.677
NPP_COL, LST_COL = "modis-17A3HGF-061", "modis-11A2-061"


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _item(root, iid, start, end, assets, dt_none):
    return SimpleNamespace(id=iid, datetime=None if dt_none else start,
                           properties={"start_datetime": iso(start), "end_datetime": iso(end)},
                           assets={a: SimpleNamespace(href=f"{root}/{iid}.{a}.tif") for a in assets},
                           _start=start, _end=end)


def tile_items(root, h, v, years=range(2014, 2026), end_mode="clip", ties=(), drop=lambda it: False):
    """(npp items, lst items) for tile h, v. ties: list of (year, doy, id_suffix) -> an extra Terra LST item
    with the same start as that composite and id '<base>.<id_suffix>' (a reprocessed granule)."""
    npp, lst = [], []
    t = f"h{h:02d}v{v:02d}"
    for y in years:
        s, e = datetime(y, 1, 1, tzinfo=UTC), datetime(y, 12, 31, 23, 59, 59, tzinfo=UTC)
        npp.append(_item(root, f"MOD17A3HGF.A{y}001.{t}.061.{y + 1}020000000", s, e, ["Npp_500m"], y % 2 == 0))
        npp.append(_item(root, f"MYD17A3HGF.A{y}001.{t}.061.{y + 1}020000000", s, e, ["Npp_500m"], False))
        for doy in range(1, 366, 8):
            s = datetime(y, 1, 1, tzinfo=UTC) + timedelta(days=doy - 1)
            e = s + timedelta(days=8, seconds=-1)
            if end_mode == "clip":
                e = min(e, datetime(y, 12, 31, 23, 59, 59, tzinfo=UTC))
            for pre in ("MOD11A2", "MYD11A2"):
                lst.append(_item(root, f"{pre}.A{y}{doy:03d}.{t}.061.{y}{doy + 9:03d}000000", s, e,
                                 ["LST_Day_1km", "LST_Night_1km"], pre == "MOD11A2" and doy % 5 == 0))
            for (ty, tdoy, suf) in ties:
                if (ty, tdoy) == (y, doy):
                    lst.append(_item(root, f"MOD11A2.A{y}{doy:03d}.{t}.061.{suf}", s, e,
                                     ["LST_Day_1km", "LST_Night_1km"], False))
    return [i for i in npp if not drop(i)], [i for i in lst if not drop(i)]


def query_interval(dt_string):
    s = _ItemSearch.__new__(_ItemSearch)._format_datetime(dt_string)
    a, b = s.split("/")
    return parse_iso(a), parse_iso(b)


def api_order(items, order, seed=0):
    if order == "desc":                      # start desc, id desc (pgstac-like; not verified)
        return sorted(items, key=lambda i: (i._start, i.id), reverse=True)
    if order == "asc":
        return sorted(items, key=lambda i: (i._start, i.id))
    its = list(items)
    random.Random(seed).shuffle(its)
    return its


class FakeCatalog:
    def __init__(self, root, tiles, order="shuffle", end_mode="clip", ties=None, drop=None, empty_tiles=()):
        self.root, self.tiles, self.order, self.end_mode = root, list(tiles), order, end_mode
        self.ties = ties or {}                  # tile -> list of (year, doy, suffix)
        self.drop = drop or (lambda it: False)
        self.empty = set(empty_tiles)
        self.calls = []

    def items(self, h, v):
        return tile_items(self.root, h, v, end_mode=self.end_mode, ties=self.ties.get((h, v), ()), drop=self.drop)

    def search(self, collections, datetime=None, query=None, max_items=None, **kw):
        h, v = int(query["modis:horizontal-tile"]["eq"]), int(query["modis:vertical-tile"]["eq"])
        q0, q1 = query_interval(datetime)
        self.calls.append((collections[0], datetime, h, v, max_items))
        if (h, v) in self.empty or (h, v) not in self.tiles:
            its = []
        else:
            npp, lst = self.items(h, v)
            its = npp if collections[0] == NPP_COL else lst
            its = [i for i in its if i._start <= q1 and i._end >= q0]
            its = api_order(its, self.order, seed=int(hashlib.sha256(f"{h}-{v}-{collections[0]}".encode()).hexdigest()[:8], 16))
        if max_items is not None:
            its = its[:max_items]
        return SimpleNamespace(item_collection=lambda: list(its))


class FakeTokens:
    def __init__(self, *a, **k):
        self.n = 0

    def get(self, force=False):
        self.n += 1
        return "tok"


# ------------------------------------------------------------------ rasters

def grid(h, v, px, lat, lon, margin=15e3):
    from rasterio.transform import from_origin
    tl, tt = X0 + h * T_TILE, Y0 - v * T_TILE
    xs = R_EARTH * np.radians(lon) * np.cos(np.radians(lat))
    ys = R_EARTH * np.radians(lat)
    x0, x1 = max(tl, xs.min() - margin), min(tl + T_TILE, xs.max() + margin)
    y1, y0 = min(tt, ys.max() + margin), max(tt - T_TILE, ys.min() - margin)
    c0, c1 = int(np.floor((x0 - tl) / px)), int(np.ceil((x1 - tl) / px))
    r0, r1 = int(np.floor((tt - y1) / px)), int(np.ceil((tt - y0) / px))
    return from_origin(tl + c0 * px, tt - r0 * px, px, px), c1 - c0, r1 - r0


def write_rasters(cat, pts, fill_point=None):
    """Write a raster for every Terra item of every tile in ``cat`` (2019-2025 items only)."""
    import rasterio
    n = 0
    for (h, v) in cat.tiles:
        sub = pts[(pts.h == h) & (pts.v == v)]
        npp, lst = tile_items(cat.root, h, v, years=range(2019, 2026), end_mode="overlap",
                              ties=cat.ties.get((h, v), ()))
        for it in npp + lst:
            if not it.id.startswith(("MOD17A3HGF", "MOD11A2")):
                continue
            for a, asset in it.assets.items():
                path = asset.href + "?tok"
                if os.path.exists(path):
                    continue
                rng = np.random.default_rng(int(hashlib.sha256(asset.href.split("/")[-1].encode()).hexdigest()[:12], 16))
                if a == "Npp_500m":
                    tr, W, H = grid(h, v, T_TILE / 2400, sub.lat.values, sub.lon.values)
                    coarse = rng.integers(200, 12000, size=(H // 9 + 2, W // 9 + 2))
                    arr = np.kron(coarse, np.ones((9, 9), int))[:H, :W] + rng.integers(-180, 180, (H, W))
                    u = rng.random((H, W))
                    arr[u < .05] = 32767
                    arr[(u >= .05) & (u < .08)] = rng.integers(32761, 32767)
                    arr[(u >= .08) & (u < .10)] = 0
                    arr[(u >= .10) & (u < .105)] = -3000
                    if fill_point is not None and (h, v) == (fill_point.h, fill_point.v):
                        x = R_EARTH * np.radians(fill_point.lon) * np.cos(np.radians(fill_point.lat))
                        y = R_EARTH * np.radians(fill_point.lat)
                        c, r = int((x - tr.c) / tr.a), int((y - tr.f) / tr.e)
                        arr[max(r - 25, 0):r + 25, max(c - 25, 0):c + 25] = 32767
                    dtype = "int16"
                else:
                    tr, W, H = grid(h, v, T_TILE / 1200, sub.lat.values, sub.lon.values)
                    coarse = rng.integers(12800, 16200, size=(H // 5 + 2, W // 5 + 2))
                    arr = np.kron(coarse, np.ones((5, 5), int))[:H, :W] + rng.integers(-60, 60, (H, W))
                    arr[rng.random((H, W)) < .18] = 0
                    if rng.random() < .15:
                        arr[:] = 0
                    dtype = "uint16"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                                   dtype=dtype, transform=tr, crs=SIN, compress="deflate") as dst:
                    dst.write(arr.astype(dtype), 1)
                n += 1
    return n
