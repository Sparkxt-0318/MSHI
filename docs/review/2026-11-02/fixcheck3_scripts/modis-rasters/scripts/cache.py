"""MODIS cache key / sidecar checks with a package copy PKG (head = de236d0 == a6c00bc mshi/; edit = head with
extract_points multiplying every window mean by 1.1; prev = 9e17a36). One sandbox SB shared across calls
(separate processes, one package each). Same fakes as stage.py.
usage: cache.py WORKDIR PKG SB ACTION
ACTION: run | load | hash | replace_same_values | crash_before_meta | libs | features_require | stale_json"""
import copy, hashlib, json, sys, types
SCR = "fixcheck3_scripts/modis-rasters"
W, PKG, SB, ACTION = sys.argv[1:5]
sys.path.insert(0, f"{SCR}/fake")
sys.path.insert(0, f"{SCR}/pkg/{PKG}")
import pandas as pd
import fakepc3
import mshi
from mshi.config import Config, load_config
from mshi.io import write_result, write_table, read_json
import mshi.io as IO
import mshi.netutil as N
from mshi.data import modis
assert mshi.__file__.startswith(f"{SCR}/pkg/{PKG}/"), mshi.__file__
meta = pd.read_csv(f"{W}/sites_meta.csv")
TILES3 = sorted({(int(h), int(v)) for h, v, k in zip(meta.h, meta.v, meta.kind) if k != "tile4"})
ROOT = f"{W}/tiles"


class FakeClient:
    @staticmethod
    def open(url, **kw):
        return fakepc3.FakeCatalog(ROOT, TILES3, order="shuffle")


mod = types.ModuleType("pystac_client")
mod.Client = FakeClient
sys.modules["pystac_client"] = mod
modis.TokenCache = fakepc3.FakeTokens
N.check_reachable = lambda *a, **k: None
reads = []
_rw = modis.read_windows
modis.read_windows = lambda href, sub, kind, m: (reads.append(href), _rw(href, sub, kind, m))[1]

base = load_config()
d = copy.deepcopy(base.data)
d["paths"]["raw"] = f"{W}/sb/{SB}/raw"
c = Config(d, source=base.source, out_root=f"{W}/sb/{SB}/out")
bs = c.path("results", "build_sites.json")
pts = pd.read_csv(f"{W}/sites3.csv")
st = pd.DataFrame({"site_id": [f"s{i}" for i in range(len(pts))], "lat": pts.lat, "lon": pts.lon,
                   "continent": "Europe", "log_rs": 6.0})
outs = [write_table(st, c.path("derived", f"sites_v3_{t}.parquet")) for t in ("qc", "repo")]
try:
    write_result(c, {"fake": True}, "build_sites.json", outputs=outs)     # current for THIS package's code hash
except TypeError:                                                        # 9e17a36: no outputs argument
    write_result(c, {"fake": True}, "build_sites.json")
pq, mj = c.path("interim", "modis_points.parquet"), c.path("interim", "modis_points.meta.json")


def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None


def load():
    try:
        df = modis.load_modis_points(c)
        return f"ACCEPTED npp_max={float(df.npp.max())!r}"
    except Exception as e:  # noqa: BLE001
        return f"REFUSED {type(e).__name__}: {str(e).split("modis_points.parquet")[-1][:300]}"


def run():
    n0 = len(reads)
    try:
        r = modis.modis_points(c)
        s = f"ok cached={bool(r.get('cached'))}"
    except Exception as e:  # noqa: BLE001
        s = f"{type(e).__name__}: {str(e)[:160]}"
    return {"status": s, "reads": len(reads) - n0, "parquet": h(pq), "meta": h(mj),
            "npp_max": float(pd.read_parquet(pq).npp.max()) if pq.exists() else None}


out = {"pkg": PKG, "code_hash": modis._extraction_code_sha256()[:12],
       "libraries": getattr(modis, "_library_versions", lambda: None)()}
if ACTION == "run":
    out["load_before"] = load() if pq.exists() else "no cache"
    out["run"] = run()
    out["load_after"] = load()
    if mj.exists():
        m = read_json(mj)
        out["meta_keys"] = sorted(m)
        out["key_fields"] = sorted(m.get("key", {}))
elif ACTION == "load":
    out["load"] = load()
elif ACTION == "replace_same_values":
    df = pd.read_parquet(pq)
    before = h(pq)
    df.to_parquet(pq, index=False, compression="gzip")            # same values, other bytes
    out["parquet_before_after"] = [before, h(pq)]
    out["values_equal"] = bool(pd.read_parquet(pq).equals(df))
    out["load"] = load()
    try:
        IO.require_outputs(c, "modis_points.json", [pq])
        out["require_outputs"] = "accepted"
    except Exception as e:  # noqa: BLE001
        out["require_outputs"] = f"REFUSED {type(e).__name__}: {str(e)[:160]}"
    out["run"] = run()
elif ACTION == "crash_before_meta":
    real = modis.write_json

    def boom(obj, path):
        if str(path).endswith("modis_points.meta.json"):
            raise KeyboardInterrupt("simulated crash after the table was written")
        return real(obj, path)
    modis.write_json = boom
    for p in (pq, mj):
        p.unlink(missing_ok=True)
    try:
        modis.modis_points(c)
        out["crash"] = "no crash?"
    except KeyboardInterrupt as e:
        out["crash"] = str(e)
    modis.write_json = real
    out["after_crash"] = {"parquet": h(pq), "meta": h(mj), "load": load()}
    out["rerun"] = run()
elif ACTION == "libs":
    lib = modis._library_versions()
    modis._library_versions = lambda: {**lib, "proj": "0.0.0"}
    out["load_other_proj"] = load()
    out["run_other_proj"] = run()
print(json.dumps(out, indent=1, default=str))
