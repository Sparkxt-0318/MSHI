"""fetch_worldclim / fetch_soilgrids sidecars and features.verify_inputs of a package copy (default pkg/head),
in a smoke sandbox (out_root + paths.raw in scratch). HTTP goes only to a local ThreadingHTTPServer on
127.0.0.1 (every requests.Session made with trust_env=False): /wc/wc2.1_2.5m_bio.zip (19 synthetic GeoTIFF
layers) and /wcs (a fake SoilGrids WCS returning a small GeoTIFF per COVERAGEID). Requests are counted.
usage: rasters_check.py WORKDIR [PKG]"""
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
c = sandbox("A")
# site tables + MODIS cache so that verify_inputs / features can run
pts = pd.DataFrame({"lat": [45.0, 46.02, -3.1], "lon": [10.0, 11.43, -60.0]})
st = pts.assign(site_id=["a", "b", "c"], continent="Europe", log_rs=6.0)
outs = [write_table(st, c.path("derived", f"sites_v3_{t}.parquet")) for t in ("qc", "repo")]
write_result(c, {"fake": True}, "build_sites.json", outputs=outs)
keys = modis.site_key(pts.lat, pts.lon).values
tab = pd.DataFrame({"site_key": keys, "npp": 500.0, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                    "lst_night": 5.0, "lst_night_n": 60})
p = modis.write_modis_cache(c, tab, modis.modis_cache_key(c, keys), {"n_failed_reads": 0})
write_result(c, {"n_failed_reads": 0}, "modis_points.json", outputs=[p])

out["1_fresh_worldclim"] = call(rasters.fetch_worldclim, c)
out["1_fresh_soilgrids"] = call(rasters.fetch_soilgrids, c)
out["1_files"] = ls(c)
out["1_features"] = call(F.features, c)
out["2_rerun_worldclim"] = call(rasters.fetch_worldclim, c)
out["2_rerun_soilgrids"] = call(rasters.fetch_soilgrids, c)

# 3. replaced files
t1 = rasters.worldclim_path(c, 1)
t1.write_bytes(t1.read_bytes()[:-10] + b"0123456789")
out["3_verify_after_wc_layer_replaced"] = verify(c)
out["3_refetch_worldclim"] = call(rasters.fetch_worldclim, c)
s1 = rasters.soilgrids_path(c, "soc")
s1.write_bytes(s1.read_bytes() + b"x")
out["3_verify_after_sg_replaced"] = verify(c)
out["3_refetch_soilgrids"] = call(rasters.fetch_soilgrids, c)
out["3_verify_after_refetch"] = verify(c)

# 4. configured request changes
q = sandbox("A", edit=lambda d: d["sources"]["soilgrids"].__setitem__("statistic", "Q0.5"))
out["4_statistic_Q0.5"] = call(rasters.fetch_soilgrids, q)
out["4_statistic_files"] = sorted(x.name for x in rasters.soilgrids_path(q, "soc").parent.glob("soc_*.tif"))
la = sandbox("A", edit=lambda d: d["sources"]["soilgrids"].__setitem__("lat", [-60, 84]))
out["4_lat_change"] = call(rasters.fetch_soilgrids, la)
out["4_verify_lat_config_without_features_rerun"] = verify(la)       # fetch results now current for `la`
out["4_back_to_A_soilgrids"] = call(rasters.fetch_soilgrids, c)     # A's request again: re-fetched (same names)

# 5. pin the WorldClim zip hash to the value recorded by the first download (configs/v3.yaml:57 suggests it)
rec = read_json(c.path("results", "fetch_worldclim.json"))
pin = rec["zip_sha256"]
pinned = sandbox("A", edit=lambda d: d["sources"]["worldclim"].__setitem__("sha256", pin))
MODE["wc"] = "down"
out["5_pin_recorded_hash_server_down"] = call(rasters.fetch_worldclim, pinned)
out["5_files_after"] = ls(pinned)
MODE["wc"] = "ok"
out["5_pin_recorded_hash_server_up"] = call(rasters.fetch_worldclim, pinned)
out["5_files_after_up"] = ls(pinned)
out["5_zip_hash_equals_pin"] = hashlib.sha256((rasters.worldclim_dir(pinned).parent / "wc2.1_2.5m_bio.zip").read_bytes()).hexdigest() == pin

# 6. a zip with no sidecar (e.g. downloaded by 9e17a36's fetch_worldclim, or placed by hand) and no layers
wd = rasters.worldclim_dir(c)
for t in wd.glob("*"):
    t.unlink()
(wd.parent / "wc2.1_2.5m_bio.zip.source.json").unlink()
MODE["wc"] = "down"
out["6_zip_without_sidecar_server_down"] = call(rasters.fetch_worldclim, c)
out["6_files_after"] = ls(c)
MODE["wc"] = "ok"
out["6_refetch_server_up"] = call(rasters.fetch_worldclim, c)
print(json.dumps(out, indent=1, default=str))
srv.shutdown()
