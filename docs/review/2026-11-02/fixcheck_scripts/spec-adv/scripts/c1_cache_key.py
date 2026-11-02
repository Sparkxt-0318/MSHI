"""Claim 1: does the MODIS cache key notice a value-changing edit inside extract_points?

Usage: python -B c1_cache_key.py <package_root> <sandbox_out_root>
Everything offline: fake STAC catalog, fake token, fake read_windows (value 100 per window).
"""
import copy
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

root, sand = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)

import pandas as pd  # noqa: E402

import mshi  # noqa: E402
from mshi.config import Config, load_config  # noqa: E402
from mshi.data import modis as M  # noqa: E402
import mshi.netutil as N  # noqa: E402
from mshi.io import result_staleness  # noqa: E402
from mshi.runlog import code_sha256  # noqa: E402

assert mshi.__file__.startswith(root), mshi.__file__
base = load_config("/home/user/MSHI/configs/v3.yaml")
d = copy.deepcopy(base.data)
d["paths"]["raw"] = f"{sand}/raw"
cfg = Config(d, source=base.source, out_root=sand)

pts = pd.DataFrame({"lat": [45.0, 45.01], "lon": [10.0, 10.02]})
pts["site_key"] = M.site_key(pts.lat, pts.lon).values
M.modis_point_set = lambda c: pts
N.check_reachable = lambda *a, **k: None


class Cat:
    def search(self, collections, **kw):
        if collections[0].startswith("modis-17"):
            its = [SimpleNamespace(id=f"MOD17A3HGF.A{y}", datetime=datetime(y, 1, 1, tzinfo=timezone.utc),
                                   properties={}, assets={"Npp_500m": SimpleNamespace(href=f"mem://npp{y}")})
                   for y in range(2020, 2025)]
        else:
            its = [SimpleNamespace(id="MOD11A2.A2021001", datetime=datetime(2021, 1, 1, tzinfo=timezone.utc),
                                   properties={}, assets={"LST_Day_1km": SimpleNamespace(href="mem://d"),
                                                          "LST_Night_1km": SimpleNamespace(href="mem://n")})]
        return SimpleNamespace(item_collection=lambda: its)


import pystac_client  # noqa: E402
pystac_client.Client.open = staticmethod(lambda *a, **k: Cat())
M.TokenCache.get = lambda self, force=False: "tok"
reads = {"n": 0}


def fake_read(href, sub, kind, m):
    reads["n"] += 1
    return {k: 100.0 for k in sub.site_key}


M.read_windows = fake_read
r = M.modis_points(cfg)
df = M.load_modis_points(cfg, pts.site_key)      # what features() calls
res = json.loads(cfg.path("results", "modis_points.json").read_text())
meta = json.loads(cfg.path("interim", "modis_points.meta.json").read_text())
print(json.dumps({
    "package": root,
    "pkg_code_sha256": code_sha256()[:12],
    "extraction_code_sha256": M._extraction_code_sha256()[:12],
    "returned_key_code": r["cache_key"]["code_sha256"][:12],
    "meta_key_code": meta["key"]["code_sha256"][:12],
    "cached": r.get("cached", False),
    "fake_reads": reads["n"],
    "npp": df.npp.tolist(), "lst_day": df.lst_day.tolist(),
    "results_json_prov_code": res["_provenance"]["code_sha256"][:12],
    "result_staleness_modis_points_json": result_staleness(cfg, res),
}))
