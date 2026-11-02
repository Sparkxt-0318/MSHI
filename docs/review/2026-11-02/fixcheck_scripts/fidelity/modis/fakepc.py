"""Fake Planetary Computer for the MODIS fidelity check: a STAC catalog over local synthetic sinusoidal
GeoTIFFs. Files are written as '<name>.tif?tok' so that href + '?' + token ('tok') opens them locally."""
import hashlib, json, os, random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.abspath(__file__))
TILES = os.path.join(ROOT, "tiles")


def _item(iid, when, assets, dt_none):
    return SimpleNamespace(id=iid, datetime=None if dt_none else when,
                           properties={"start_datetime": when.isoformat().replace("+00:00", "Z")},
                           assets={a: SimpleNamespace(href=f"{TILES}/{iid}.{a}.tif") for a in assets})


def catalog_items(h, v, years=range(2020, 2025), lst_years=range(2020, 2022), ties=False):
    """(npp items, lst items) for tile h, v, in a scrambled 'API' order."""
    npp, lst = [], []
    for y in years:
        w = datetime(y, 1, 1, tzinfo=timezone.utc)
        npp.append(_item(f"MOD17A3HGF.A{y}001.h{h:02d}v{v:02d}.061", w, ["Npp_500m"], dt_none=(y % 2 == 0)))
        npp.append(_item(f"MYD17A3HGF.A{y}001.h{h:02d}v{v:02d}.061", w, ["Npp_500m"], dt_none=False))
    for y in lst_years:
        for doy in range(1, 366, 8):
            w = datetime(y, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)
            lst.append(_item(f"MOD11A2.A{y}{doy:03d}.h{h:02d}v{v:02d}.061", w, ["LST_Day_1km", "LST_Night_1km"],
                             dt_none=(doy % 5 == 0)))
            lst.append(_item(f"MYD11A2.A{y}{doy:03d}.h{h:02d}v{v:02d}.061", w, ["LST_Day_1km", "LST_Night_1km"],
                             dt_none=False))
            if ties and doy == 1:   # a second Terra item with the same date (reprocessed granule)
                lst.append(_item(f"MOD11A2.A{y}{doy:03d}.h{h:02d}v{v:02d}.061.B", w, ["LST_Day_1km", "LST_Night_1km"],
                                 dt_none=False))
    r = random.Random(f"{h}-{v}")
    r.shuffle(npp)
    r.shuffle(lst)
    return npp, lst


class FakeCatalog:
    def __init__(self, tiles, ties=False, log=None):
        self.tiles = set(tiles)          # tiles that have items; others return nothing
        self.ties = ties
        self.calls = [] if log is None else log

    def search(self, collections, datetime=None, query=None, max_items=None, **kw):
        h = int(query["modis:horizontal-tile"]["eq"])
        v = int(query["modis:vertical-tile"]["eq"])
        self.calls.append((collections[0], datetime, h, v, max_items))
        if (h, v) not in self.tiles:
            its = []
        else:
            npp, lst = catalog_items(h, v, ties=self.ties)
            its = npp if collections[0] == "modis-17A3HGF-061" else lst
        return SimpleNamespace(item_collection=lambda: list(its))


class FakeClient:
    tiles = None
    ties = False

    @classmethod
    def open(cls, url, **kw):
        assert url == "https://planetarycomputer.microsoft.com/api/stac/v1", url
        return FakeCatalog(cls.tiles, cls.ties)


class FakeTokens:
    def __init__(self, *a, **k):
        self.n = 0

    def get(self, force=False):
        self.n += 1
        return "tok"
