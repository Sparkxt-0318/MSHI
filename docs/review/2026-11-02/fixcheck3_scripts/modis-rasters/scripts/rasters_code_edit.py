"""A code edit to the SoilGrids WCS request (pkg/sgedit: OUTPUTCRS EPSG:4326 -> EPSG:3857 in fetch_soilgrids)
vs the per-file sidecar: is the file fetched again? Local fake WCS (trust_env=False), smoke sandbox.
usage: rasters_code_edit.py WORKDIR PKG"""
import copy, hashlib, http.server, io, json, sys, threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
SCR = "fixcheck3_scripts/modis-rasters"
W, PKG = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, f"{SCR}/pkg/{PKG}")
import numpy as np, rasterio, requests
from rasterio.transform import from_origin
import mshi
from mshi.config import Config, load_config
from mshi.io import read_json, require_outputs
from mshi.data import rasters
from mshi.runlog import code_sha256
assert mshi.__file__.startswith(f"{SCR}/pkg/{PKG}/")
_S = requests.Session
class DS(_S):
    def __init__(self):
        super().__init__(); self.trust_env = False
requests.Session = DS
HITS = []
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query); HITS.append(q.get("OUTPUTCRS", ["?"])[0])
        a = np.full((139, 360), 7, "int16"); 
        with rasterio.MemoryFile() as mf:
            with mf.open(driver="GTiff", width=360, height=139, count=1, dtype="int16", crs="EPSG:4326",
                         transform=from_origin(-180, 82.7, 1, 1)) as d: d.write(a, 1)
            body = mf.read()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = load_config()
d = copy.deepcopy(base.data)
d["paths"]["raw"] = str(W / "raw")
d["sources"]["soilgrids"]["wcs_url"] = f"http://127.0.0.1:{srv.server_address[1]}/wcs"   # same URL path each run;
c = Config(d, source=base.source, out_root=W / "out")
# the port differs per process, so pin wcs_url to a fixed value for the request hash: re-use the first one
side0 = W / "wcs_url.txt"
if side0.exists():
    d["sources"]["soilgrids"]["wcs_url"] = side0.read_text()
    c = Config(d, source=base.source, out_root=W / "out")
    rasters_url = side0.read_text()
    import mshi.netutil as N
    _dl = N.download
    def dl(url, dest, **k):                       # same configured URL, routed to this process's server
        return _dl(f"http://127.0.0.1:{srv.server_address[1]}/wcs", dest, **k)
    rasters.download = dl
else:
    side0.parent.mkdir(parents=True, exist_ok=True)
    side0.write_text(d["sources"]["soilgrids"]["wcs_url"])
    import mshi.netutil as N
    _dl = N.download
    def dl(url, dest, **k):
        return _dl(url, dest, **k)
    rasters.download = dl
r = rasters.fetch_soilgrids(c)
p = rasters.soilgrids_path(c, "soc")
sc = read_json(p.with_name(p.name + ".source.json"))
res = read_json(c.path("results", "fetch_soilgrids.json"))
try:
    require_outputs(c, "fetch_soilgrids.json", [rasters.soilgrids_path(c, v) for v in d["sources"]["soilgrids"]["variables"]])
    acc = "accepted"
except Exception as e:
    acc = f"REFUSED {e}"
print(json.dumps({"pkg": PKG, "code_sha256": code_sha256()[:12], "http_requests": len(HITS), "OUTPUTCRS_sent": sorted(set(HITS)),
                  "sidecar_params_OUTPUTCRS": sc["params"]["OUTPUTCRS"], "result_code_sha256": res["_provenance"]["code_sha256"][:12],
                  "require_outputs_fetch_soilgrids": acc, "soc_sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:12]}, indent=1))
srv.shutdown()
