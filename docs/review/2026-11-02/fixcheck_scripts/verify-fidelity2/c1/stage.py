"""Drive the real modis_points / load_modis_points of one package copy against the fake PC (local rasters).
usage: stage.py PKGDIR SANDBOX ACTION [TILEDIR]
ACTION: hash | run | load | staleness | replace (overwrite the parquet with npp+100, npp_n=1, sidecar kept)
Only modis_point_set, TokenCache, pystac_client and netutil.check_reachable are replaced (none of them is
among the functions hashed by _extraction_code_sha256)."""
import copy, hashlib, json, sys, types
pkg, sb, action = sys.argv[1:4]
tiles = sys.argv[4] if len(sys.argv) > 4 else sb + "/tiles"
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/verify-fidelity2/fake")
sys.path.insert(0, pkg)
import pandas as pd
import fakepc2
import mshi
from mshi.config import Config, load_config
import mshi.netutil as N
from mshi.data import modis

assert mshi.__file__.startswith(pkg), mshi.__file__
cfg = load_config()
data = copy.deepcopy(cfg.data)
data["paths"]["raw"] = sb + "/raw"
sand = Config(data, source=cfg.source, out_root=sb + "/out")
pts = pd.DataFrame({"lat": [p[0] for p in fakepc2.PTS], "lon": [p[1] for p in fakepc2.PTS]})
pts["site_key"] = modis.site_key(pts.lat, pts.lon, 5).values
modis.modis_point_set = lambda c: pts.copy()
N.check_reachable = lambda *a, **k: None
mod = types.ModuleType("pystac_client")
import os
mod.Client = types.SimpleNamespace(open=lambda url, **k: fakepc2.FakeCatalog(tiles, make_files=os.environ.get("FAKEPC_NOCREATE") != "1"))
sys.modules["pystac_client"] = mod
modis.TokenCache = fakepc2.FakeTokens
pq, meta = sand.path("interim", "modis_points.parquet"), sand.path("interim", "modis_points.meta.json")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12] if p.exists() else None


tag = pkg.rstrip("/").rsplit("/", 1)[-1]
if action == "hash":
    from mshi.runlog import code_sha256
    ex = getattr(modis, "_extraction_code_sha256", None)
    print(f"[{tag}] _extraction_code_sha256 = {ex() if ex else 'n/a'} | package code_sha256 = {code_sha256()}")
elif action == "run":
    r = modis.modis_points(sand)
    out = pd.read_parquet(pq)
    print(f"[{tag}] modis_points -> cached={r.get('cached')} n_raster_reads={r.get('n_raster_reads')} "
          f"n_failed_reads={r.get('n_failed_reads')} | parquet sha={sha(pq)} meta sha={sha(meta)}")
    print(out.round(6).to_string(index=False))
elif action == "load":
    df = modis.load_modis_points(sand, set(pts.site_key))
    print(f"[{tag}] load_modis_points ACCEPTED parquet sha={sha(pq)}")
    print(df.round(6).to_string(index=False))
elif action == "staleness":
    from mshi.io import read_json, result_staleness
    j = read_json(sand.path("results", "modis_points.json"))
    print(f"[{tag}] results/modis_points.json staleness under this package: {result_staleness(sand, j)!r}; "
          f"record n_failed_reads={j.get('n_failed_reads')} cached={j.get('cached')}")
elif action == "replace":
    df = pd.read_parquet(pq)
    df["npp"] = df["npp"] + 100.0
    df["npp_n"] = 1
    df.to_parquet(pq, index=False)
    print(f"[{tag}] parquet replaced (npp+100, npp_n=1); meta untouched sha={sha(meta)}")
