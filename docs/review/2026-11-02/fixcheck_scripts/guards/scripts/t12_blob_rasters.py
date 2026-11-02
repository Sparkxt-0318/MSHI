import json, os, shutil, socket, sys, threading
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.CRITICAL)
from types import SimpleNamespace
from datetime import datetime, timezone
import numpy as np, pandas as pd, rasterio
from rasterio.transform import from_origin
from mshi.run import run
from mshi.data import modis as MD
import mshi.netutil as N

W = Path(SCR) / "work" / "t12"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
# ---- (1) COG host behind a proxy that denies CONNECT (fake proxy; no real host contacted)
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", 0)); srv.listen(20)
seen = []
def loop():
    while True:
        c, _ = srv.accept(); seen.append(c.recv(4096).split(b"\r\n")[0].decode()); c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"); c.close()
threading.Thread(target=loop, daemon=True).start()
for k in ("HTTPS_PROXY", "https_proxy"):
    os.environ[k] = f"http://127.0.0.1:{srv.getsockname()[1]}"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
it = lambda y: SimpleNamespace(id=f"MOD17A3HGF.A{y}", datetime=datetime(y, 1, 1, tzinfo=timezone.utc), properties={},
                               assets={"Npp_500m": SimpleNamespace(href=f"https://modiseuwest.blob.core.windows.net/modis-061-cogs/npp_{y}.tif")})
class Cat:
    def search(self, collections, **k):
        return SimpleNamespace(item_collection=lambda: [it(y) for y in range(2020, 2025)] if "17A3" in collections[0] else [])
import pystac_client
pystac_client.Client.open = staticmethod(lambda url: Cat())
class Tok:
    def __init__(self, *a, **k): pass
    def get(self, force=False): return "tok"
MD.TokenCache = Tok
pts = pd.DataFrame({"lat": [45.0], "lon": [10.0]}); pts["site_key"] = MD.site_key(pts.lat, pts.lon).values
MD.modis_point_set = lambda c: pts.copy()
orig_cr = N.check_reachable
N.check_reachable = lambda url, *a, **k: None if "planetarycomputer" in url else orig_cr(url, *a, **k)   # STAC/token faked
cfg = sandbox(W / "blob", absolute=True)
code = run(["modis_points"], cfg)
rec = json.loads(cfg.path("results", "run_log.jsonl").read_text().splitlines()[-1])
print("(1) COG host denied by the proxy: exit", code, "| status:", rec["status"][:100], "| proxy saw:", seen[:1])
N.check_reachable = orig_cr
for k in ("HTTPS_PROXY", "https_proxy"):
    os.environ.pop(k)

# ---- (2) rasters changed after fetch: does features notice?
cfg2 = sandbox(W / "rast", absolute=True)
def tif(p, val, dtype="float32"):
    p.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(p, "w", driver="GTiff", width=360, height=180, count=1, dtype=dtype, crs="EPSG:4326",
                       transform=from_origin(-180, 90, 1, 1)) as d:
        d.write(np.full((180, 360), val, dtype=dtype), 1)
from mshi.data.rasters import worldclim_path, soilgrids_path
for i in range(1, 20):
    tif(worldclim_path(cfg2, i), 10.0 + i)
for v in cfg2["sources"]["soilgrids"]["variables"]:
    tif(soilgrids_path(cfg2, v), 300, "int16")
cfg2.path("derived").mkdir(parents=True)
for t in ("qc", "repo"):
    shutil.copy(Path(REPO) / f"data/derived/sites_v3_{t}.parquet", cfg2.path("derived", f"sites_v3_{t}.parquet"))
keys = set()
for t in ("qc", "repo"):
    s = pd.read_parquet(cfg2.path("derived", f"sites_v3_{t}.parquet")); keys |= set(MD.site_key(s.lat, s.lon))
mod = pd.DataFrame({"site_key": sorted(keys), "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60, "lst_night": 5.0, "lst_night_n": 60})
cfg2.path("interim").mkdir(parents=True); mod.to_parquet(cfg2.path("interim", "modis_points.parquet"), index=False)
from mshi.io import write_json
write_json({"key": MD.modis_cache_key(cfg2, mod.site_key), "record": {"n_failed_reads": 0}}, cfg2.path("interim", "modis_points.meta.json"))
print("(2) fetch_worldclim/fetch_soilgrids with files present:", run(["fetch_worldclim", "fetch_soilgrids"], cfg2))
tif(worldclim_path(cfg2, 1), 99.0)          # bio01 replaced after the fetch recorded its hash
rec_hash = json.loads(cfg2.path("results", "fetch_worldclim.json").read_text())["tif_sha256"]["wc2.1_2.5m_bio_1.tif"]
from mshi.io import sha256_file
print("    bio01 hash now differs from the recorded one:", sha256_file(worldclim_path(cfg2, 1)) != rec_hash)
print("    features: exit", run(["features"], cfg2), "| bio01 used:",
      pd.read_parquet(cfg2.path("interim", "features_v3_qc.parquet")).bio01.unique()[:3])
