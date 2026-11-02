"""Claim 4: with sources.modis.max_failed_reads > 0 and some persistent read failures, what do
modis_points, load_modis_points (features), the cache and repro_checks do?

Usage: python -B c4_max_failed.py <sandbox_dir>
Offline: fake STAC catalog, fake token, fake read_windows (NPP 2023 reads always fail).
"""
import copy
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/MSHI")
import pandas as pd  # noqa: E402

from mshi.config import Config, load_config  # noqa: E402
from mshi.data import modis as M  # noqa: E402
import mshi.netutil as N  # noqa: E402
import mshi.run as R  # noqa: E402

S = Path(sys.argv[1])
shutil.rmtree(S, ignore_errors=True)
base = load_config()
d = copy.deepcopy(base.data)
for k in ("raw", "interim", "derived", "results", "figures"):   # absolute sandbox paths, out_root None
    d["paths"][k] = str(S / k)                                   # (out_root would make run() a smoke run)
d["sources"]["modis"]["max_failed_reads"] = 5
d["sources"]["modis"]["retries"] = 1
cfg = Config(d, source=base.source)
assert str(cfg.path("results")).startswith(str(S)) and str(cfg.path("interim")).startswith(str(S))

# 5 points in 5 different MODIS tiles -> 5 NPP-2023 reads, all failing persistently
pts = pd.DataFrame({"lat": [45.0, 30.0, 10.0, -20.0, 60.0], "lon": [10.0, 80.0, -60.0, 25.0, -100.0]})
pts["site_key"] = M.site_key(pts.lat, pts.lon).values
M.modis_point_set = lambda c: pts
N.check_reachable = lambda *a, **k: None


class Cat:
    def search(self, collections, **kw):
        if collections[0].startswith("modis-17"):
            its = [SimpleNamespace(id=f"MOD17A3HGF.A{y}", datetime=datetime(y, 1, 1, tzinfo=timezone.utc),
                                   properties={}, assets={"Npp_500m": SimpleNamespace(href=f"mem://npp{y}/{id(kw)}")})
                   for y in range(2020, 2025)]
        else:
            its = [SimpleNamespace(id="MOD11A2.A2021001", datetime=datetime(2021, 1, 1, tzinfo=timezone.utc),
                                   properties={}, assets={"LST_Day_1km": SimpleNamespace(href="mem://d"),
                                                          "LST_Night_1km": SimpleNamespace(href="mem://n")})]
        return SimpleNamespace(item_collection=lambda: its)


import pystac_client  # noqa: E402
pystac_client.Client.open = staticmethod(lambda *a, **k: Cat())
M.TokenCache.get = lambda self, force=False: "tok"
calls = {"n": 0}


def fake_read(href, sub, kind, m):
    calls["n"] += 1
    if "npp2023" in href:
        raise OSError("CURL error: 503")
    return {k: (500.0 if kind == "npp" else 20.0) for k in sub.site_key}


M.read_windows = fake_read

code = R.run(["modis_points", "repro_checks"], cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
print("exit code:", code, "| run_log:", [(r["stage"], r["status"][:60]) for r in recs])
rec = json.loads(cfg.path("results", "modis_points.json").read_text())
print("modis_points.json: n_failed_reads =", rec["n_failed_reads"], "| status key:", rec.get("status"),
      "| parquet exists:", cfg.path("interim", "modis_points.parquet").exists())
df = pd.read_parquet(cfg.path("interim", "modis_points.parquet"))
print("parquet npp_n:", df.npp_n.tolist())
rows = json.loads(cfg.path("results", "reproduction_check.json").read_text())["rows"]
for r in rows:
    if r["quantity"].startswith("NPP"):
        print("NPP row:", r["status"], "|", r["note"][:140])
try:
    M.load_modis_points(cfg, pts.site_key)            # what features() calls
    print("load_modis_points: accepted")
except Exception as e:  # noqa: BLE001
    print("load_modis_points (features):", type(e).__name__, str(e)[-90:])
n0 = calls["n"]
r2 = M.modis_points(cfg)
print("second modis_points: cached =", r2.get("cached", False), "| reads attempted again:", calls["n"] - n0)
