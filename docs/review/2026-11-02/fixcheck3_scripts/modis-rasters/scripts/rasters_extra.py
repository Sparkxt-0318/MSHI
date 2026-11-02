"""fetch_worldclim / fetch_soilgrids sidecars and features.verify_inputs of a package copy (default pkg/head),
in a smoke sandbox (out_root + paths.raw in scratch). HTTP goes only to a local ThreadingHTTPServer on
127.0.0.1 (every requests.Session made with trust_env=False): /wc/wc2.1_2.5m_bio.zip (19 synthetic GeoTIFF
layers) and /wcs (a fake SoilGrids WCS returning a small GeoTIFF per COVERAGEID). Requests are counted.
usage: rasters_extra.py WORKDIR [PKG]  (layer count change; interrupted fetches)"""
import copy, hashlib, http.server, io, json, sys, threading, zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
SCR = "fixcheck3_scripts/modis-rasters"
W = Path(sys.argv[1])
PKG = sys.argv[2] if len(sys.argv) > 2 else "head"
sys.path.insert(0, f"{SCR}/pkg/{PKG}")
import numpy as np, pandas as pd, rasterio, requests
from rasterio.transform import from_origin
import mshi
from mshi.config import Config, load_config
from mshi.io import StaleInputError, read_json, write_result, write_table
from mshi.data import rasters, features as F, modis
assert mshi.__file__.startswith(f"{SCR}/pkg/{PKG}/"), mshi.__file__

_Session = requests.Session


class DirectSession(_Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False               # local server only: bypass the egress proxy


requests.Session = DirectSession


def tif_bytes(w, h, seed, dtype="float32"):
    r = np.random.default_rng(seed)
    a = (r.random((h, w)) * 100 + 1).astype(dtype)
    buf = io.BytesIO()
    with rasterio.MemoryFile() as mf:
        with mf.open(driver="GTiff", width=w, height=h, count=1, dtype=dtype, crs="EPSG:4326",
                     transform=from_origin(-180, 90, 360 / w, 180 / h)) as dst:
            dst.write(a, 1)
        return mf.read()


ZIP = io.BytesIO()
with zipfile.ZipFile(ZIP, "w") as z:
    for i in range(1, 20):
        z.writestr(f"wc2.1_2.5m_bio_{i}.tif", tif_bytes(360, 180, i))
ZIP = ZIP.getvalue()
HITS = []
MODE = {"wc": "ok"}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        HITS.append(u.path + ("?" + "&".join(f"{k}={v[0]}" for k, v in sorted(parse_qs(u.query).items())
                                             if k in ("COVERAGEID", "SCALESIZE", "OUTPUTCRS")) if u.query else ""))
        if u.path.startswith("/wc/"):
            if MODE["wc"] == "down":
                self.send_response(503); self.send_header("Content-Length", "0"); self.end_headers(); return
            body = ZIP
        elif u.path == "/wcs":
            q = parse_qs(u.query)
            body = tif_bytes(360, 139, int(hashlib.sha256(q["COVERAGEID"][0].encode()).hexdigest()[:6], 16), "int16")
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"
import mshi.netutil as N
_dl = N.download
N_DL = []


def counting_download(*a, **k):                     # real download, no sleeps, fewer retries (speed)
    N_DL.append(a[0])
    k.setdefault("sleep", lambda s: None)
    k["retries"] = 2
    return _dl(*a, **k)


rasters.download = counting_download
base = load_config()


def sandbox(name, edit=None):
    d = copy.deepcopy(base.data)
    d["paths"]["raw"] = str(W / "rsb" / "raw")             # one raw dir shared by all configs (as on a machine)
    d["sources"]["worldclim"]["url"] = f"{URL}/wc/wc2.1_2.5m_bio.zip"
    d["sources"]["soilgrids"]["wcs_url"] = f"{URL}/wcs"
    if edit:
        edit(d)
    return Config(d, source=base.source, out_root=W / "rsb" / name)


def call(f, c):
    n0, h0 = len(N_DL), len(HITS)
    try:
        f(c)
        s = "ok"
    except Exception as e:  # noqa: BLE001
        s = f"{type(e).__name__}: {str(e)[:220]}"
    return {"status": s, "downloads": len(N_DL) - n0, "http_requests": len(HITS) - h0}


def ls(c):
    wd = rasters.worldclim_dir(c)
    z = wd.parent / "wc2.1_2.5m_bio.zip"
    return {"n_tifs": len(list(wd.glob("*.tif"))) if wd.exists() else 0, "zip": z.exists(),
            "zip_sidecar": z.with_name(z.name + ".source.json").exists(),
            "layer_sidecar": (wd / "worldclim.source.json").exists()}


def verify(c):
    try:
        F.verify_inputs(c)
        return "accepted"
    except StaleInputError as e:
        return f"REFUSED StaleInputError: {str(e)[:200]}"


out = {}
c = sandbox("X")
out["1_fresh_worldclim"] = call(rasters.fetch_worldclim, c)
out["1_fresh_soilgrids"] = call(rasters.fetch_soilgrids, c)
# (a) another number of layers (features.worldclim_vars): the same zip is needed, only fewer layers extracted
n12 = sandbox("X", edit=lambda d: d["features"].__setitem__("worldclim_vars", 12))
MODE["wc"] = "down"
out["a_worldclim_vars_12_server_down"] = call(rasters.fetch_worldclim, n12)
out["a_files_after"] = ls(n12)
MODE["wc"] = "ok"
out["a_worldclim_vars_12_server_up"] = call(rasters.fetch_worldclim, n12)
# (b) interrupted SoilGrids fetch: the process dies after the file is downloaded, before its sidecar is written
real_wj = rasters.write_json
def boom(obj, path):
    if str(path).endswith("soc_5-15cm_mean_global_0p05.tif.source.json"):
        raise KeyboardInterrupt("simulated kill before the sidecar")
    return real_wj(obj, path)
p = rasters.soilgrids_path(c, "soc")
p.unlink(); p.with_name(p.name + ".source.json").unlink()
rasters.write_json = boom
try:
    rasters.fetch_soilgrids(c)
except KeyboardInterrupt as e:
    out["b_killed"] = str(e)
rasters.write_json = real_wj
out["b_file_present_without_sidecar"] = p.exists() and not p.with_name(p.name + ".source.json").exists()
out["b_rerun"] = call(rasters.fetch_soilgrids, c)
# (c) interrupted WorldClim extraction: killed while extracting (layer sidecar already removed at that point)
t5 = rasters.worldclim_path(c, 5)
t5.write_bytes(b"corrupted")              # forces re-extraction
import zipfile as _z
real_extract = _z.ZipFile.extract
cnt = {"n": 0}
def ext(self, member, path=None, pwd=None):
    cnt["n"] += 1
    if cnt["n"] == 3:
        raise KeyboardInterrupt("simulated kill during extraction")
    return real_extract(self, member, path, pwd)
_z.ZipFile.extract = ext
try:
    rasters.fetch_worldclim(c)
except KeyboardInterrupt as e:
    out["c_killed"] = str(e)
_z.ZipFile.extract = real_extract
out["c_files_after_kill"] = ls(c)
out["c_rerun"] = call(rasters.fetch_worldclim, c)
out["c_files_after_rerun"] = ls(c)
print(json.dumps(out, indent=1, default=str))
srv.shutdown()
