"""Claim 2: a STAC catalog returning fewer items than the date range implies is not a failure.

Real modis_points -> extract_points -> plan_jobs -> _read_job -> read_windows -> aggregate, with the REAL
sources.modis config, on local sinusoidal GeoTIFFs. Faked: STAC client (pystac_client.Client.open), SAS token,
check_reachable (would contact Planetary Computer), the point set; read_windows is wrapped only to drop the
'?token' suffix from local file paths. Nothing leaves the machine.
"""
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import WORK, sandbox  # noqa: E402

logging.basicConfig(level=logging.ERROR)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pystac_client  # noqa: E402
import rasterio  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

import mshi.netutil as N  # noqa: E402
from mshi.data import modis  # noqa: E402

W = WORK / "v2"; shutil.rmtree(W, ignore_errors=True); (W / "tif").mkdir(parents=True)
base_cfg = sandbox(W / "cfg0", full=False)
M = base_cfg["sources"]["modis"]
pts = pd.DataFrame({"lat": [45.0, 45.01], "lon": [10.0, 10.02]})
pts["site_key"] = modis.site_key(pts.lat, pts.lon).values
x, y = Transformer.from_crs("EPSG:4326", M["sinusoidal_proj"], always_xy=True).transform(10.0, 45.0)


def tif(name, value, res):
    p = W / "tif" / name
    with rasterio.open(p, "w", driver="GTiff", width=200, height=200, count=1, dtype="int16", crs=M["sinusoidal_proj"],
                       transform=from_origin(x - 100 * res, y + 100 * res, res, res)) as dst:
        dst.write(np.full((200, 200), value, "int16"), 1)
    return str(p)


NPP = {yr: v for yr, v in zip(range(2020, 2025), (300, 400, 500, 900, 1000))}     # g C m-2 yr-1
npp_items = [SimpleNamespace(id=f"MOD17A3HGF.A{yr}001.h18v04", datetime=datetime(yr, 1, 1, tzinfo=timezone.utc),
                             properties={}, assets={M["npp"]["asset"]: SimpleNamespace(href=tif(f"npp{yr}.tif", int(v / M['npp']['scale']), 463.3))})
             for yr, v in NPP.items()]
lst_items = []
for yr in range(2020, 2025):
    for mth in range(1, 13):
        when = datetime(yr, mth, 1, tzinfo=timezone.utc)
        assets = {a: SimpleNamespace(href=tif(f"lst_{a}_{yr}{mth:02d}.tif", 15000 if "Day" in a else 14000, 926.6))
                  for a in M["lst"]["assets"].values()}
        lst_items.append(SimpleNamespace(id=f"MOD11A2.A{yr}{mth:02d}01.h18v04", datetime=when, properties={}, assets=assets))


class Catalog:
    def __init__(self, npp_years, lst_months):
        self.npp = [i for i in npp_items if i.datetime.year in npp_years]
        self.lst = [i for i in lst_items if (i.datetime.year, i.datetime.month) in lst_months]

    def search(self, collections, **kw):
        its = self.npp if collections[0] == M["npp"]["collection"] else self.lst
        return SimpleNamespace(item_collection=lambda: list(its))


class Tok:
    def __init__(self, *a, **k):
        pass

    def get(self, force=False):
        return "tok"


_orig_read = modis.read_windows
modis.read_windows = lambda href, sub, kind, m: _orig_read(href.split("?")[0], sub, kind, m)
modis.TokenCache = Tok
modis.modis_point_set = lambda c: pts
N.check_reachable = lambda *a, **k: None
ALL_MONTHS = {(y, m) for y in range(2020, 2025) for m in range(1, 13)}
state = {}
pystac_client.Client.open = lambda url, *a, **k: state["catalog"]


def scenario(label, npp_years, lst_months, cfg):
    state["catalog"] = Catalog(npp_years, lst_months)
    try:
        r = modis.modis_points(cfg)
        status = "ok"
    except Exception as e:  # noqa: BLE001
        r, status = {}, f"error: {type(e).__name__}: {e}"
    try:
        t = modis.load_modis_points(cfg, pts.site_key)
        acc = f"accepted: npp={t.npp.round(2).tolist()} npp_n={t.npp_n.tolist()} lst_day_n={t.lst_day_n.tolist()}"
    except Exception as e:  # noqa: BLE001
        acc = f"refused: {type(e).__name__}"
    print(f"[{label}] status {status}; " + ", ".join(f"{k}={r.get(k)}" for k in
          ("n_raster_reads", "n_failed_reads", "missing", "cached")) + f"\n     load_modis_points: {acc}")


scenario("complete catalog (5 NPP years, 60 LST months)", set(NPP), ALL_MONTHS, sandbox(W / "c1", full=False))
c2 = sandbox(W / "c2", full=False)
scenario("catalog returns 3 of 5 NPP years", {2020, 2021, 2022}, ALL_MONTHS, c2)
scenario("  ... same cache, catalog complete again (re-run)", set(NPP), ALL_MONTHS, c2)
scenario("catalog returns 0 NPP items", set(), ALL_MONTHS, sandbox(W / "c3", full=False))
scenario("catalog returns LST for 2020 only (12 of 60 months)", set(NPP), {(2020, m) for m in range(1, 13)},
         sandbox(W / "c4", full=False))
print("max_items_per_tile:", M["max_items_per_tile"], "| datetime:", M["datetime"],
      "| MOD11A2 8-day composites per year 46 -> Terra+Aqua items in range ~", 46 * 5 * 2)
