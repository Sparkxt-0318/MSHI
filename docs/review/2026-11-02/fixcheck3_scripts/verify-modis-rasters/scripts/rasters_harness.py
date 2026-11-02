"""Verifier's own check of fetch_worldclim / fetch_soilgrids sidecars (real functions of a package copy).

HTTP goes only to a local ThreadingHTTPServer on 127.0.0.1 (every requests.Session is created with
trust_env=False, so no proxy): /wc/wc2.1_2.5m_bio.zip (19 small synthetic GeoTIFF layers) and /wcs (fake
SoilGrids WCS returning a GeoTIFF). The server can answer 503 ('down'). download() is the real
mshi.netutil.download with its backoff sleeps replaced by a no-op (retry count unchanged).
Smoke sandbox: out_root and paths.raw in scratch.

usage: rasters_harness.py SCENARIO [PKG]
  worldclim            : claim 4 steps (pin the recorded hash; vars 19->12; zip without sidecar)
  soilgrids_first PKG  : fresh fetch_soilgrids with package PKG into sandbox 'sg'
  soilgrids_again PKG  : fetch_soilgrids again with package PKG on the same sandbox, then require_outputs
"""
import copy
import hashlib
import http.server
import io
import json
import os
import sys
import threading
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

V = "fixcheck3_scripts/verify-modis-rasters"
SC = sys.argv[1]
PKG = sys.argv[2] if len(sys.argv) > 2 else "head"
sys.path.insert(0, f"{V}/pkg/{PKG}")
import numpy as np
import rasterio
import requests
from rasterio.transform import from_origin

import mshi
import mshi.netutil as N
from mshi.config import Config, load_config
from mshi.data import rasters as R
from mshi.io import read_json, require_outputs
from mshi.runlog import code_sha256
assert mshi.__file__.startswith(f"{V}/pkg/{PKG}/"), mshi.__file__

_S = requests.Session


class DirectSession(_S):
    def __init__(self):
        super().__init__()
        self.trust_env = False


requests.Session = DirectSession
_real_download = N.download
DL = []


def download(*a, **k):
    DL.append(a[0])
    return _real_download(*a, **{**k, "sleep": lambda s: None})


R.download = download


def tif(w, h, seed, dtype="float32"):
    a = (np.random.default_rng(seed).random((h, w)) * 100 + 1).astype(dtype)
    with rasterio.MemoryFile() as mf:
        with mf.open(driver="GTiff", width=w, height=h, count=1, dtype=dtype, crs="EPSG:4326",
                     transform=from_origin(-180, 90, 360 / w, 180 / h)) as dst:
            dst.write(a, 1)
        return mf.read()


zb = io.BytesIO()
with zipfile.ZipFile(zb, "w") as z:
    for i in range(1, 20):
        z.writestr(f"wc2.1_2.5m_bio_{i}.tif", tif(120, 60, i))
ZIP = zb.getvalue()
HITS, MODE = [], {"up": True}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        HITS.append((u.path, q.get("COVERAGEID", [""])[0], q.get("OUTPUTCRS", [""])[0]))
        if not MODE["up"]:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = ZIP if u.path.startswith("/wc/") else tif(100, 50, int(hashlib.sha256(
            (q.get("COVERAGEID", [""])[0] + q.get("OUTPUTCRS", [""])[0]).encode()).hexdigest()[:8], 16))
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "0"))), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASEURL = f"http://127.0.0.1:{srv.server_address[1]}"
BASE = load_config()


def cfg(name, edit=None):
    d = copy.deepcopy(BASE.data)
    d["paths"]["raw"] = f"{V}/work/rasters/{name}/raw"
    d["sources"]["worldclim"]["url"] = f"{BASEURL}/wc/wc2.1_2.5m_bio.zip"
    d["sources"]["soilgrids"]["wcs_url"] = f"{BASEURL}/wcs"
    if edit:
        edit(d)
    return Config(d, source=BASE.source, out_root=f"{V}/work/rasters/{name}/out")


def call(f, c):
    h0, d0 = len(HITS), len(DL)
    try:
        f(c)
        st = "ok"
    except Exception as e:  # noqa: BLE001
        st = f"{type(e).__name__}: {str(e)[:160]}"
    return {"status": st, "http_requests": len(HITS) - h0, "download_calls": len(DL) - d0}


def wc_files(c):
    d = R.worldclim_dir(c)
    z = d.parent / "wc2.1_2.5m_bio.zip"
    return {"n_layers": len(list(d.glob("wc2.1_2.5m_bio_*.tif"))) if d.exists() else 0, "zip": z.exists(),
            "zip_sidecar": z.with_name(z.name + ".source.json").exists(),
            "layer_sidecar": (d / "worldclim.source.json").exists(),
            "zip_sha12": hashlib.sha256(z.read_bytes()).hexdigest()[:12] if z.exists() else None}


out = {"pkg": mshi.__file__, "code_sha12": code_sha256()[:12]}
if SC == "worldclim":
    import shutil
    shutil.rmtree(f"{V}/work/rasters/wc", ignore_errors=True)
    c = cfg("wc")
    out["1_fresh"] = call(R.fetch_worldclim, c)
    rec = read_json(c.path("results", "fetch_worldclim.json"))
    X = rec["zip_sha256"]
    out["1_recorded_zip_sha256"] = X
    out["1_files"] = wc_files(c)
    out["2_rerun_unchanged"] = call(R.fetch_worldclim, c)
    # 3: pin sha256 to the hash recorded by the first download; server down
    cp = cfg("wc", lambda d: d["sources"]["worldclim"].__setitem__("sha256", X))
    MODE["up"] = False
    out["3_pinned_recorded_hash_server_down"] = call(R.fetch_worldclim, cp)
    out["3_files_after"] = wc_files(cp)
    MODE["up"] = True
    out["4_pinned_server_up"] = call(R.fetch_worldclim, cp)
    out["4_files_after"] = wc_files(cp)
    out["4_new_zip_sha256_equals_pin"] = read_json(cp.path("results", "fetch_worldclim.json"))["zip_sha256"] == X
    out["4b_rerun_pinned"] = call(R.fetch_worldclim, cp)
    # 5: worldclim_vars 19 -> 12 (pinned config as in step 4), server down
    c12 = cfg("wc", lambda d: (d["sources"]["worldclim"].__setitem__("sha256", X),
                               d["features"].__setitem__("worldclim_vars", 12)))
    MODE["up"] = False
    out["5_vars12_server_down"] = call(R.fetch_worldclim, c12)
    out["5_files_after"] = wc_files(c12)
    MODE["up"] = True
    out["5b_vars12_server_up"] = call(R.fetch_worldclim, c12)
    out["5b_files_after"] = wc_files(c12)
    # 6: a zip + layers left by 9e17a36 (no sidecars), unpinned config, server down
    shutil.rmtree(f"{V}/work/rasters/wc_old", ignore_errors=True)
    co = cfg("wc_old")
    d = R.worldclim_dir(co)
    d.mkdir(parents=True)
    (d.parent / "wc2.1_2.5m_bio.zip").write_bytes(ZIP)
    with zipfile.ZipFile(io.BytesIO(ZIP)) as z:
        for i in range(1, 20):
            z.extract(f"wc2.1_2.5m_bio_{i}.tif", d)
    out["6_before"] = wc_files(co)
    MODE["up"] = False
    out["6_no_sidecar_server_down"] = call(R.fetch_worldclim, co)
    out["6_files_after"] = wc_files(co)
    MODE["up"] = True
elif SC == "soilgrids_first":
    import shutil
    shutil.rmtree(f"{V}/work/rasters/sg", ignore_errors=True)
    c = cfg("sg")
    out["fresh"] = call(R.fetch_soilgrids, c)
    out["outputcrs_sent"] = sorted({h[2] for h in HITS})
elif SC == "soilgrids_again":
    c = cfg("sg")
    p = R.soilgrids_path(c, "soc")
    before = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    out["again"] = call(R.fetch_soilgrids, c)
    out["outputcrs_sent"] = sorted({h[2] for h in HITS})
    side = read_json(p.with_name(p.name + ".source.json"))
    out["sidecar_params_OUTPUTCRS"] = side["params"]["OUTPUTCRS"]
    out["code_params_OUTPUTCRS_in_this_pkg"] = [ln.strip() for ln in open(R.__file__) if '"OUTPUTCRS"' in ln]
    res = read_json(c.path("results", "fetch_soilgrids.json"))
    out["fetch_soilgrids.json code_sha12"] = res["_provenance"]["code_sha256"][:12]
    try:
        require_outputs(c, "fetch_soilgrids.json", [R.soilgrids_path(c, v) for v in c["sources"]["soilgrids"]["variables"]])
        out["require_outputs"] = "accepted"
    except Exception as e:  # noqa: BLE001
        out["require_outputs"] = f"{type(e).__name__}: {e}"
    out["soc_sha12_before_after"] = [before, hashlib.sha256(p.read_bytes()).hexdigest()[:12]]
elif SC == "wrongpin":
    import shutil
    shutil.rmtree(f"{V}/work/rasters/wcpin", ignore_errors=True)
    c = cfg("wcpin")
    out["1_fresh_unpinned"] = call(R.fetch_worldclim, c)
    out["1_files"] = wc_files(c)
    cw = cfg("wcpin", lambda d: d["sources"]["worldclim"].__setitem__("sha256", "0" * 64))
    out["2_wrong_pin_server_up"] = call(R.fetch_worldclim, cw)
    out["2_files_after"] = wc_files(cw)
srv.shutdown()
print(json.dumps(out, indent=1, default=str))
