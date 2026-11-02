"""Claim 6: modis_points.meta.json does not bind the bytes of modis_points.parquet.

Real modis_points()/load_modis_points(); the extraction itself is faked (complete, no failed reads); point set,
check_reachable faked; everything under scratch.
"""
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import WORK, sandbox  # noqa: E402

logging.basicConfig(level=logging.WARNING)
import pandas as pd  # noqa: E402

import mshi.netutil as N  # noqa: E402
from mshi.data import modis  # noqa: E402
from mshi.io import read_json, sha256_file  # noqa: E402

W = WORK / "v6"; shutil.rmtree(W, ignore_errors=True)
cfg = sandbox(W, full=False)
pts = pd.DataFrame({"lat": [45.0, 45.01], "lon": [10.0, 10.02]})
pts["site_key"] = modis.site_key(pts.lat, pts.lon).values
modis.modis_point_set = lambda c: pts
N.check_reachable = lambda *a, **k: None
calls = {"n": 0}


def fake_extract(p, m):
    calls["n"] += 1
    return (pd.DataFrame({"site_key": p.site_key, "npp": 620.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                          "lst_night": 5.0, "lst_night_n": 60}),
            {"n_jobs": 125, "n_tiles": 1, "failed_reads": []})


modis.extract_points = fake_extract
r = modis.modis_points(cfg)
out, meta = modis._paths(cfg)
print("run 1:", {k: r[k] for k in ("n_points", "n_failed_reads", "n_raster_reads")}, "| extraction calls", calls["n"])
m = read_json(meta)
print("meta top-level keys:", sorted(m), "| key fields:", sorted(m["key"]), "| record fields:", sorted(m["record"]))
print("meta mentions the parquet sha256:", sha256_file(out) in json.dumps(m))

df = pd.read_parquet(out)
df["npp"] = df["npp"] * 2                      # out-of-band edit; meta untouched
df.to_parquet(out, index=False)
got = modis.load_modis_points(cfg, pts.site_key)
print("after editing the parquet: load_modis_points accepts it, npp =", got.npp.tolist())
r2 = modis.modis_points(cfg)
print("modis_points again:", {"cached": r2.get("cached")}, "| extraction calls", calls["n"])
