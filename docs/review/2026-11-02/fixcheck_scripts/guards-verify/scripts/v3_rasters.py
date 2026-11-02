"""Claim 3: WorldClim/SoilGrids rasters are not verified at read time, and fetch stages skip existing files whatever
the config says. Real fetch_worldclim / fetch_soilgrids / features on synthetic rasters in a scratch sandbox.
HTTP goes only to a local counting server (or nowhere); the real WorldClim/SoilGrids hosts are never contacted.
"""
import http.server
import json
import logging
import os
import shutil
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path, sandbox  # noqa: E402

logging.basicConfig(level=logging.ERROR)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from mshi.data import features as F  # noqa: E402
from mshi.data import rasters  # noqa: E402
from mshi.data.modis import modis_cache_key, site_key  # noqa: E402
from mshi.io import read_json, sha256_file, write_json, write_table  # noqa: E402

HITS = []


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        HITS.append(self.path)
        self.send_response(500); self.send_header("Content-Length", "0"); self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
LOCAL = f"http://127.0.0.1:{srv.server_address[1]}"
dl_calls = []
_orig_download = rasters.download
rasters.download = lambda url, dest, **k: (dl_calls.append(url), _orig_download(url, dest, **k))[1]

W = WORK / "v3"; shutil.rmtree(W, ignore_errors=True)


def write_raster(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    a = np.full((180, 360), value, "float32") + np.random.default_rng(0).uniform(0, 1, (180, 360)).astype("float32")
    with rasterio.open(p, "w", driver="GTiff", width=360, height=180, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(a, 1)


def setup(cfg):
    shutil.copytree(Path(REPO) / "data" / "derived", cfg.path("derived"))
    for i in range(1, cfg["features"]["worldclim_vars"] + 1):
        write_raster(rasters.worldclim_path(cfg, i), 10.0)
    for v in cfg["sources"]["soilgrids"]["variables"]:
        write_raster(rasters.soilgrids_path(cfg, v), 50.0)
    keys = set()
    for tag in cfg["site_build"]["variants"]:
        st = pd.read_parquet(cfg.path("derived", f"sites_v3_{tag}.parquet"))
        keys |= set(site_key(st.lat, st.lon, cfg["features"]["site_key_round"]))
    keys = sorted(keys)
    write_table(pd.DataFrame({"site_key": keys, "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                              "lst_night": 5.0, "lst_night_n": 60}), cfg.path("interim", "modis_points.parquet"))
    write_json({"key": modis_cache_key(cfg, keys), "record": {"n_failed_reads": 0}},
               cfg.path("interim", "modis_points.meta.json"))


cfg = sandbox(W, full=False)
setup(cfg)
wc, sg = rasters.fetch_worldclim(cfg), rasters.fetch_soilgrids(cfg)
print(f"(1) rasters on disk: fetch_worldclim ok (downloads {len(dl_calls)}, zip_sha256={wc['zip_sha256']}), "
      f"fetch_soilgrids ok (downloads {len(dl_calls)})")
pinned = wc["tif_sha256"]["wc2.1_2.5m_bio_1.tif"]
write_raster(rasters.worldclim_path(cfg, 1), 99.0)          # bio01 replaced after the fetch stage recorded its hash
print("    bio01 sha256 now == fetch_worldclim.json tif_sha256:", sha256_file(rasters.worldclim_path(cfg, 1)) == pinned)
res = F.features(cfg)
f = pd.read_parquet(cfg.path("interim", "features_v3_qc.parquet"))
print(f"    features ran (shape {res['qc']['shape']}); bio01 range used: {f.bio01.min():.2f}..{f.bio01.max():.2f} "
      "(replaced raster, no hash comparison)")

# (2) config edits of the SoilGrids request with the files present
edit = {"statistic": "Q0.5", "depth": "0-5cm", "size": [3600, 1387], "lat": [-60, 84], "wcs_url": LOCAL + "/wcs"}
cfg2 = sandbox(W, full=False, edit=lambda d: d["sources"]["soilgrids"].update(edit))
before = {rasters.soilgrids_path(cfg2, v).name: sha256_file(rasters.soilgrids_path(cfg2, v))
          for v in cfg2["sources"]["soilgrids"]["variables"]}
assert before == sg["files_sha256"], "first fetch_soilgrids record should hash the same files"
n0 = len(dl_calls)
sg2 = rasters.fetch_soilgrids(cfg2)
j = read_json(cfg2.path("results", "fetch_soilgrids.json"))
print(f"(2) SoilGrids config edited {edit}:")
print(f"    fetch_soilgrids ok; download calls {len(dl_calls) - n0}; HTTP requests to the local WCS {len(HITS)}")
print(f"    fetch_soilgrids.json records statistic={j['statistic']!r} depth={j['depth']!r} size={j['size']} "
      f"wcs_url={j['wcs_url']}; files unchanged: {before == j['files_sha256']}")
print("    file path depends on:", cfg2["sources"]["soilgrids"]["file_pattern"], "+ version", cfg2["sources"]["soilgrids"]["version"])

# (3) WorldClim url / sha256 pin edited with the tifs present
cfg3 = sandbox(W, full=False, edit=lambda d: d["sources"]["worldclim"].update(
    {"url": LOCAL + "/other/wc2.1_2.5m_bio.zip", "sha256": "0" * 64}))
n0 = len(dl_calls)
wc3 = rasters.fetch_worldclim(cfg3)
print(f"(3) WorldClim url -> local server and sha256 pinned to 000…0: fetch_worldclim ok; download calls "
      f"{len(dl_calls) - n0}; HTTP {len(HITS)}; records url={wc3['url'][-30:]} zip_sha256_pinned={wc3['zip_sha256_pinned'][:6]}… "
      f"zip_sha256={wc3['zip_sha256']}")

# (4) does any reader compare raster hashes?
for mod in ("mshi/data/features.py", "mshi/data/rasters.py"):
    src = (Path(REPO) / mod).read_text()
    print(f"(4) {mod}: mentions verify_sha256={('verify_sha256' in src)}, read_json(fetch_={('fetch_worldclim.json' in src and 'read_json' in src)}")
print("    io.py docstring lines 11-12:", (Path(REPO) / "mshi/io.py").read_text().splitlines()[10:12])
