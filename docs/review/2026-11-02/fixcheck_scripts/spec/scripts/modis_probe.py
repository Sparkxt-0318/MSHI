"""spec-01 re-check: drive the real run() -> modis_points -> extract_points -> plan_jobs -> aggregate with a fake
STAC catalog, fake token, fake raster reads and an emulated proxy, in scratch (out_root None, absolute paths)."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
import numpy as np, pandas as pd, requests
from mshi.config import load_config, Config
from mshi.io import read_table
import mshi.netutil as N
from mshi.data import modis as M
import mshi.run as R
import pystac_client

S = Path(sys.argv[1]); shutil.rmtree(S, ignore_errors=True)
base = load_config()

def mkcfg(edit=None):
    d = copy.deepcopy(base.data)
    for k in ("raw", "interim", "derived", "results", "figures"):
        d["paths"][k] = str(S / k)
    if edit: edit(d)
    return Config(d, source=base.source)

(S / "derived").mkdir(parents=True)
for f in ("sites_v3_qc.parquet", "sites_v3_repo.parquet"):
    shutil.copy(base.path("derived", f), S / "derived" / f)

BLOB = "https://modiseuwest.blob.core.windows.net/modis-061-cogs"
def item(iid, when, assets):
    w = datetime(*when, tzinfo=timezone.utc)
    return SimpleNamespace(id=iid, datetime=w, properties={"start_datetime": w.isoformat()},
                           assets={a: SimpleNamespace(href=f"{BLOB}/{iid}/{a}.tif") for a in assets})
class Cat:
    def search(self, collections, query=None, **kw):
        h, v = query["modis:horizontal-tile"]["eq"], query["modis:vertical-tile"]["eq"]
        if collections[0].startswith("modis-17"):
            its = [item(f"MOD17A3HGF.A{y}.h{h}v{v}", (y, 1, 1), ["Npp_500m"]) for y in range(2020, 2025)]
        else:
            its = [item(f"MOD11A2.A{y}{m:02d}{d:02d}.h{h}v{v}", (y, m, d), ["LST_Day_1km", "LST_Night_1km"])
                   for y in (2020,) for m in range(1, 13) for d in (1, 9)]
        return SimpleNamespace(item_collection=lambda: its)
pystac_client.Client.open = staticmethod(lambda url, *a, **k: Cat())
M.TokenCache.get = lambda self, force=False: "tok"

# committed NPP for realistic r
frames = [read_table(base, base.repo_path(rel)) for rel in base["legacy_allowlist"]]
o = pd.concat(frames, ignore_index=True)
o["site_key"] = M.site_key(o.latitude, o.longitude).values
rng = np.random.default_rng(1)
NPPV = dict(zip(o.site_key, o.npp * 0.1 * (1 + rng.normal(0, 0.08, len(o)))))
STATE = {"mode": "ok", "reads": 0, "calls": {}}
def fake_read(href, sub, kind, m):
    STATE["reads"] += 1
    h = href.split("?")[0]
    STATE["calls"][h] = STATE["calls"].get(h, 0) + 1
    if STATE["mode"] == "persistent" and "A2023" in h and "h25v" in h:
        raise OSError("CURL error: HTTP response code said error (503)")
    if STATE["mode"] == "transient" and "A2022" in h and STATE["calls"][h] <= 4:
        raise OSError("CURL error: timeout")
    out = {}
    for k in sub.site_key:
        out[k] = (NPPV.get(k, 500.0) if np.isfinite(NPPV.get(k, 500.0)) else 450.0) if kind == "npp" else 20.0
    return out
M.read_windows = fake_read
M._read_job.__defaults__ = (lambda s: None,)     # no real sleeps between attempts

real_get = requests.get
BLOCKED = set()
def fake_get(url, *a, **k):
    host = url.split("/")[2]
    if host in BLOCKED:
        raise requests.exceptions.ProxyError("Unable to connect to proxy: Tunnel connection failed: 403 Forbidden")
    return SimpleNamespace(status_code=200, reason="OK", close=lambda: None)
N.requests.get = fake_get

def go(tag, cfg, stages=("modis_points", "repro_checks")):
    STATE["reads"] = 0; STATE["calls"] = {}
    code = R.run(list(stages), cfg)
    recs = [json.loads(l) for l in (S / "results" / "run_log.jsonl").read_text().splitlines()]
    st = {r["stage"]: r["status"][:110] for r in recs[-len(stages):]}
    mp = S / "results" / "modis_points.json"
    rec = json.loads(mp.read_text()) if mp.exists() else None
    rc = json.loads((S / "results" / "reproduction_check.json").read_text()) if (S / "results" / "reproduction_check.json").exists() else None
    npp_row = [r for r in rc["rows"] if r["quantity"].startswith("NPP")][0] if rc else None
    print(f"\n== {tag}: exit={code} reads={STATE['reads']} status={st}")
    print("   modis_points.json:", None if rec is None else {k: rec.get(k) for k in ("status", "n_points", "n_raster_reads", "n_failed_reads", "cached")},
          "| parquet:", (S / "interim" / "modis_points.parquet").exists(), "| meta:", (S / "interim" / "modis_points.meta.json").exists())
    if npp_row: print("   NPP row:", npp_row["status"], npp_row["v3"], "|", npp_row["note"][:110])

cfg = mkcfg()
BLOCKED.add("modiseuwest.blob.core.windows.net")
go("1 blob host blocked (STAC+token reachable)", cfg)
BLOCKED.clear()
STATE["mode"] = "persistent"; go("2 persistent read failures", cfg)
STATE["mode"] = "transient"; go("3 transient failures (recovered in 2nd pass)", cfg)
STATE["mode"] = "ok"; go("4 re-run: cache hit expected", cfg)
cfg5 = mkcfg(lambda d: d["sources"]["modis"].__setitem__("window_deg", 0.25))
go("5 window_deg changed: re-extract expected", cfg5)
cfg6 = mkcfg(lambda d: d["sources"]["modis"].__setitem__("max_failed_reads", 5))
STATE["mode"] = "persistent"; go("6 max_failed_reads=5 with 5 failures", cfg6)
STATE["mode"] = "ok"; go("7 after 6: cache?", cfg6)
