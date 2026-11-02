"""Verifier's own fake Planetary Computer: local synthetic sinusoidal GeoTIFFs + a fake STAC client.
Files are named '<id>.<asset>.tif?tok' so that href + '?' + 'tok' (what _read_job builds) opens them.
The STAC 'API order' is configurable: 'desc' = datetime desc, id desc (the pgstac default sort, modelled
here, not verified against the real service); 'asc' = id ascending for equal datetimes; 'shuffle'."""
import hashlib
import os
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
PTS = [(45.0, 10.0), (45.013, 10.021), (44.987, 9.981), (45.031, 10.044)]   # all in one MODIS tile


def tile_of(lat, lon):
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", SIN, always_xy=True).transform(lon, lat)
    return int(np.floor((x + 20015109.354) / 1111950.5197)), int(np.floor((10007554.677 - y) / 1111950.5197))


def write_tif(path, kind, seed):
    """Small raster around PTS (not a whole tile): NPP raw 0..12000 (some 32767 fill), LST raw 13000..16000
    (some 0 = missing)."""
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import from_origin
    tf = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
    xs, ys = tf.transform([9.85, 10.2, 9.85, 10.2], [44.85, 44.85, 45.2, 45.2])
    res = 463.312716528 if kind == "npp" else 926.625433055
    x0, y1 = min(xs) - 2000, max(ys) + 2000
    w, h = int((max(xs) - x0 + 2000) / res) + 1, int((y1 - min(ys) + 2000) / res) + 1
    r = np.random.default_rng(seed)
    if kind == "npp":
        a = r.integers(0, 12000, (h, w)).astype("int16")
        a[r.random((h, w)) < 0.05] = 32767
        dtype = "int16"
    else:
        a = r.integers(13000, 16000, (h, w)).astype("uint16")
        a[r.random((h, w)) < 0.1] = 0
        dtype = "uint16"
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=1, dtype=dtype, crs=SIN,
                       transform=from_origin(x0, y1, res, res)) as dst:
        dst.write(a, 1)


def _item(root, iid, when, assets, dt_none=False):
    return SimpleNamespace(id=iid, datetime=None if dt_none else when,
                           properties={"start_datetime": when.isoformat().replace("+00:00", "Z")},
                           assets={a: SimpleNamespace(href=f"{root}/{iid}.{a}.tif") for a in assets})


def build(root, years=(2020, 2021), lst_years=(2020,), ties=False, make_files=True):
    """(npp items, lst items) for the single tile of PTS; writes the rasters on first use."""
    h, v = tile_of(*PTS[0])
    npp, lst = [], []
    for y in years:
        w = datetime(y, 1, 1, tzinfo=timezone.utc)
        for pre in ("MOD17A3HGF", "MYD17A3HGF"):
            npp.append(_item(root, f"{pre}.A{y}001.h{h:02d}v{v:02d}.061.2021{y % 100:02d}0000000", w, ["Npp_500m"],
                             dt_none=(y % 2 == 0 and pre.startswith("MOD"))))
    for y in lst_years:
        for doy in range(1, 366, 8):
            w = datetime(y, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)
            for pre in ("MOD11A2", "MYD11A2"):
                lst.append(_item(root, f"{pre}.A{y}{doy:03d}.h{h:02d}v{v:02d}.061.{y}{doy + 9:03d}000000", w,
                                 ["LST_Day_1km", "LST_Night_1km"], dt_none=(doy % 5 == 0 and pre.startswith("MOD"))))
            if ties and doy in (1, 32, 153):   # first composite of Jan, Feb, Jun: a reprocessed Terra granule
                lst.append(_item(root, f"MOD11A2.A{y}{doy:03d}.h{h:02d}v{v:02d}.061.{y + 1}150000000", w,
                                 ["LST_Day_1km", "LST_Night_1km"]))
    if make_files:
        os.makedirs(root, exist_ok=True)
        for it in npp + lst:
            for a, asset in it.assets.items():
                p = asset.href + "?tok"
                if not os.path.exists(p):
                    seed = int(hashlib.sha256((it.id + a).encode()).hexdigest()[:8], 16)
                    write_tif(p, "npp" if a == "Npp_500m" else "lst", seed)
    return (h, v), npp, lst


def api_order(items, order, seed=0):
    """Order in which the fake API returns items."""
    def when(i):
        return i.datetime or datetime.fromisoformat(i.properties["start_datetime"].replace("Z", "+00:00"))
    if order == "desc":                      # datetime desc, then id desc
        return sorted(items, key=lambda i: (when(i), i.id), reverse=True)
    if order == "asc":                       # datetime asc, then id asc
        return sorted(items, key=lambda i: (when(i), i.id))
    if order == "date_desc_id_asc":
        return sorted(sorted(items, key=lambda i: i.id), key=when, reverse=True)
    its = list(items)
    random.Random(seed).shuffle(its)
    return its


class FakeCatalog:
    def __init__(self, root, ties=False, order="desc", **kw):
        self.tile, self.npp, self.lst = build(root, ties=ties, **kw)
        self.order = order
        self.calls = []

    def search(self, collections, datetime=None, query=None, max_items=None, **kw):
        h, v = int(query["modis:horizontal-tile"]["eq"]), int(query["modis:vertical-tile"]["eq"])
        self.calls.append((collections[0], h, v))
        its = [] if (h, v) != self.tile else (self.npp if "17A3" in collections[0] else self.lst)
        its = api_order(its, self.order)
        return SimpleNamespace(item_collection=lambda: list(its))


class FakeTokens:
    def __init__(self, *a, **k):
        pass

    def get(self, force=False):
        return "tok"
