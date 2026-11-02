import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.CRITICAL)
import numpy as np, rasterio
from rasterio.transform import from_origin
import requests
from mshi.run import run
from mshi.data.rasters import soilgrids_path
W = Path(SCR) / "work" / "t14"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
calls = []
orig_get = requests.Session.get
def spy(self, url, *a, **k):
    calls.append(url); raise AssertionError("no request expected")
requests.Session.get = spy
def tif(p, val):
    p.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(p, "w", driver="GTiff", width=360, height=180, count=1, dtype="int16", crs="EPSG:4326",
                       transform=from_origin(-180, 90, 1, 1)) as d:
        d.write(np.full((180, 360), val, dtype="int16"), 1)
base = sandbox(W, absolute=True)
for v in base["sources"]["soilgrids"]["variables"]:
    tif(soilgrids_path(base, v), 300)            # "mean" rasters from an earlier fetch
def edit(d):
    sg = d["sources"]["soilgrids"]
    sg["statistic"] = "Q0.5"; sg["size"] = [3600, 1387]; sg["lat"] = [-60, 84]
changed = sandbox(W, edit=edit, absolute=True)
code = run(["fetch_soilgrids"], changed)
rec = json.loads(changed.path("results", "fetch_soilgrids.json").read_text())
with rasterio.open(soilgrids_path(changed, "soc")) as s:
    actual = (s.width, s.height)
print("soilgrids statistic->Q0.5, size->[3600,1387], lat->[-60,84] with rasters on disk: exit", code,
      "| HTTP requests:", len(calls), "| recorded statistic/size:", rec["statistic"], rec["size"], "| actual raster size:", actual)
