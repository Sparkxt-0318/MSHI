"""Real modis_points -> extract_points -> plan_jobs -> _read_job -> read_windows -> aggregate on local
sinusoidal GeoTIFFs behind a fake STAC catalog. Only the point set, the STAC client, the SAS token and the
remote reachability probes are faked."""
import json, os, shutil, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.ERROR)
from datetime import datetime, timezone
from types import SimpleNamespace
import numpy as np, pandas as pd, rasterio
from rasterio.transform import from_origin
import mshi.netutil as N
from mshi.data import modis as MD
from mshi.run import run

W = Path(SCR) / "work" / "t5"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
COG = W / "cogs"; COG.mkdir()
SINU = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
pts = pd.DataFrame({"lat": [45.0, 45.01, 45.3], "lon": [10.0, 10.02, 10.4]})
pts["site_key"] = MD.site_key(pts.lat, pts.lon).values
from pyproj import Transformer
x, y = Transformer.from_crs("EPSG:4326", SINU, always_xy=True).transform(pts.lon.values, pts.lat.values)
x0, y0 = float(x.min()) - 20000, float(y.max()) + 20000

def write_cog(name, value, res, dtype):
    n = int(80000 / res)
    a = np.full((n, n), value, dtype=dtype)
    p = COG / (name + "?tok")
    with rasterio.open(p, "w", driver="GTiff", width=n, height=n, count=1, dtype=dtype, crs=SINU,
                       transform=from_origin(x0, y0, res, res)) as d:
        d.write(a, 1)
    return str(COG / name)

NPP_DN = {2020: 3000, 2021: 4000, 2022: 5000, 2023: 9000, 2024: 10000}
def item(iid, when, assets, dt_none=False):
    w = datetime(*when, tzinfo=timezone.utc)
    return SimpleNamespace(id=iid, datetime=None if dt_none else w, properties={"start_datetime": w.isoformat()},
                           assets={k: SimpleNamespace(href=v) for k, v in assets.items()})
npp_items = {y: item(f"MOD17A3HGF.A{y}001", (y, 1, 1), {"Npp_500m": write_cog(f"npp_{y}.tif", v, 500, "int16")})
             for y, v in NPP_DN.items()}
lst_items = []
for mth in range(1, 13):
    for k, day in enumerate((1, 9, 17)):
        lst_items.append(item(f"MOD11A2.A2021{mth:02d}{day:02d}", (2021, mth, day),
                              {"LST_Day_1km": write_cog(f"lstd_{mth}_{day}.tif", 14000 + 10 * mth + day, 1000, "uint16"),
                               "LST_Night_1km": write_cog(f"lstn_{mth}_{day}.tif", 13500 + 10 * mth + day, 1000, "uint16")},
                              dt_none=(k == 0 and mth % 3 == 0)))

class Catalog:
    def __init__(self, npp_years=None):
        self.npp_years = npp_years
    def search(self, collections, datetime=None, query=None, max_items=None):
        if "17A3" in collections[0]:
            its = [npp_items[y] for y in (NPP_DN if self.npp_years is None else self.npp_years)]
        else:
            its = list(reversed(lst_items))
        return SimpleNamespace(item_collection=lambda: its)

class Tokens:
    def __init__(self, *a, **k): pass
    def get(self, force=False): return "tok"

state = {"catalog": Catalog(), "probes": 0}
import pystac_client
pystac_client.Client.open = staticmethod(lambda url: state["catalog"])
MD.TokenCache = Tokens
def probe(*a, **k): state["probes"] += 1
N.check_reachable = probe
MD.modis_point_set = lambda cfg: pts[["lat", "lon", "site_key"]].copy()
reads = {"n": 0}
_orig_read = MD.read_windows
def counting_read(href, sub, kind, m):
    reads["n"] += 1
    return _orig_read(href, sub, kind, m)
MD.read_windows = counting_read

def edit(d, **mod):
    m = d["sources"]["modis"]
    m.update({"retries": 2, "threads": 8, "second_pass_threads": 2})
    m.update(mod)
def cfg_with(**mod):
    return sandbox(W / "sb", edit=lambda d: edit(d, **mod), absolute=True)

cfg = cfg_with()
res_json = lambda c: json.loads(c.path("results", "modis_points.json").read_text())
expect_npp = np.mean([v * 0.1 for v in NPP_DN.values()])
expect_day = np.mean([(14000 + 10 * mth + 1) * 0.02 - 273.15 for mth in range(1, 13)])
print("expected npp", expect_npp, "expected lst_day (first composite/month)", round(expect_day, 6))

# 1. two NPP rasters unreadable (files absent) -> stage must fail, no values written
for y in (2023, 2024):
    os.rename(COG / f"npp_{y}.tif?tok", COG / f"npp_{y}.tif?gone")
code = run(["modis_points"], cfg)
r = res_json(cfg)
print("1. failing reads: exit", code, "| status", r.get("status"), "| n_failed", r["n_failed_reads"],
      "| parquet exists", cfg.path("interim", "modis_points.parquet").exists(),
      "| meta exists", cfg.path("interim", "modis_points.meta.json").exists())
print("   failed_reads[0]:", r["failed_reads"][0][:140])
print("   run_log:", json.loads(cfg.path("results", "run_log.jsonl").read_text().splitlines()[-1])["status"][:120])
try:
    MD.load_modis_points(cfg)
except Exception as e:
    print("   load_modis_points ->", type(e).__name__)

# 2. rasters restored -> full extraction, correct means
for y in (2023, 2024):
    os.rename(COG / f"npp_{y}.tif?gone", COG / f"npp_{y}.tif?tok")
reads["n"] = 0
code = run(["modis_points"], cfg)
t = pd.read_parquet(cfg.path("interim", "modis_points.parquet"))
print("2. restored: exit", code, "| reads", reads["n"], "| npp", t.npp.round(6).tolist(), "| npp_n", t.npp_n.tolist(),
      "| lst_day", t.lst_day.round(6).tolist()[:1], "| lst_day_n", t.lst_day_n.tolist()[:1])
j2 = cfg.path("results", "modis_points.json").read_text()
h2 = hashlib.sha256(cfg.path("interim", "modis_points.parquet").read_bytes()).hexdigest()

# 3. cache hit: no reads, same record
reads["n"] = 0; state["probes"] = 0
code = run(["modis_points"], cfg)
print("3. cache hit: exit", code, "| reads", reads["n"], "| probes", state["probes"], "| json identical:",
      cfg.path("results", "modis_points.json").read_text() == j2)

# 4. determinism: delete cache, extract again with 8 threads, compare bytes
cfg.path("interim", "modis_points.parquet").unlink()
run(["modis_points"], cfg)
print("4. re-extraction parquet SHA-256 identical:", hashlib.sha256(cfg.path("interim", "modis_points.parquet").read_bytes()).hexdigest() == h2)

# 5. MODIS config change -> stale for consumers, re-extracted by the stage
cfg5 = cfg_with(window_deg=0.25)
try:
    MD.load_modis_points(cfg5)
except Exception as e:
    print("5. load with window_deg 0.25 ->", type(e).__name__)
reads["n"] = 0
run(["modis_points"], cfg5)
print("   stage re-extracted:", reads["n"] > 0)

# 6. a tile whose STAC search returns only 3 of the 5 annual NPP items (no read fails)
state["catalog"] = Catalog(npp_years=[2020, 2021, 2022])
cfg6 = cfg_with(window_deg=0.051)          # new key, so the stage extracts
code = run(["modis_points"], cfg6)
t6 = pd.read_parquet(cfg6.path("interim", "modis_points.parquet")); r6 = res_json(cfg6)
print("6. 3 of 5 NPP items in the catalog: exit", code, "| npp", t6.npp.round(4).tolist(), "| npp_n", t6.npp_n.tolist(),
      "| n_failed", r6["n_failed_reads"], "| n_raster_reads", r6["n_raster_reads"],
      "| load_modis_points accepts:", len(MD.load_modis_points(cfg6)) == 3)
state["catalog"] = Catalog(npp_years=[])
cfg6b = cfg_with(window_deg=0.052)
code = run(["modis_points"], cfg6b)
t6b = pd.read_parquet(cfg6b.path("interim", "modis_points.parquet"))
print("   0 NPP items: exit", code, "| npp", t6b.npp.tolist(), "| npp_n", t6b.npp_n.tolist(), "| missing", res_json(cfg6b)["missing"])
state["catalog"] = Catalog()

# 7. the cached parquet is edited out of band; its meta is unchanged
run(["modis_points"], cfg)
p = cfg.path("interim", "modis_points.parquet")
t = pd.read_parquet(p); t["npp"] = t["npp"] * 2; t.to_parquet(p, index=False)
print("7. edited parquet, meta unchanged: load_modis_points npp =", MD.load_modis_points(cfg).npp.round(3).tolist(),
      "| stage reports cache hit:", "cached" in MD.modis_points(cfg))

# 8. functions outside the cache-key hash
print("8. functions hashed in the cache key:", "extract_points" in MD._extraction_code_sha256.__code__.co_names,
      "| hashed list:", [n for n in MD._extraction_code_sha256.__code__.co_names if n in dir(MD)])
