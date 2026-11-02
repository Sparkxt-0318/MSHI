"""modis_points with the real extraction code: (a) a MODIS config change -> stale refusal + re-extraction;
(b) one persistently unreadable raster -> stage fails, no values written, failure recorded, load refuses."""
import copy, json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
SB = os.path.join(HERE, "sandbox2")
sys.path.insert(0, HERE); sys.path.insert(0, "/home/user/MSHI")
import pandas as pd
import fakepc
from mshi.config import Config, load_config
import mshi.netutil as N
from mshi.data import modis

cfg = load_config()
pts = pd.read_csv(os.path.join(HERE, "sites.csv"))
modis.modis_point_set = lambda c: pts[["lat", "lon", "site_key"]].copy()
N.check_reachable = lambda url, **k: None
tiles = eval(open(os.path.join(HERE, "tiles.txt")).read())
fakepc.FakeClient.tiles = tiles
mod = types.ModuleType("pystac_client"); mod.Client = fakepc.FakeClient; sys.modules["pystac_client"] = mod
modis.TokenCache = fakepc.FakeTokens
calls = {"n": 0}
real_extract = modis.extract_points
def counting(*a, **k):
    calls["n"] += 1
    return real_extract(*a, **k)
modis.extract_points = counting


def mk(edit=None, sub="out"):
    d = copy.deepcopy(cfg.data); d["paths"]["raw"] = os.path.join(SB, "raw")
    d["sources"]["modis"]["retries"] = 1          # no sleeps in this check
    if edit: edit(d)
    return Config(d, source=cfg.source, out_root=os.path.join(SB, sub))

a = mk()
modis.modis_points(a)
base = modis.load_modis_points(a, set(pts.site_key))
b = mk(lambda d: d["sources"]["modis"].__setitem__("window_deg", 0.25))
try:
    modis.load_modis_points(b, set(pts.site_key)); print("(a) stale table accepted after window change: BAD")
except modis.StaleModisError as e:
    print("(a) load_modis_points refuses after window_deg change:", str(e)[:70])
modis.modis_points(b)
new = modis.load_modis_points(b, set(pts.site_key))
print("(a) re-extracted:", calls["n"] == 2, "| npp changed with the window:", not new.npp.equals(base.npp))

# (b) an extra NPP item whose COG cannot be read
orig = fakepc.catalog_items
def with_broken(h, v, **k):
    npp, lst = orig(h, v, **k)
    if (h, v) == tiles[0]:
        npp = npp + [fakepc._item(f"MOD17A3HGF.A2019001.h{h:02d}v{v:02d}.061", fakepc.datetime(2019, 1, 1, tzinfo=fakepc.timezone.utc),
                                  ["Npp_500m"], dt_none=False)]
    return npp, lst
fakepc.catalog_items = with_broken
c = mk(sub="out_fail")
try:
    modis.modis_points(c); print("(b) stage succeeded: BAD")
except modis.ModisIncompleteError as e:
    print("(b) ModisIncompleteError:", str(e)[:90])
rec = json.loads(c.path("results", "modis_points.json").read_text())
print("(b) record:", rec["status"], "n_failed_reads", rec["n_failed_reads"], "| parquet written:",
      c.path("interim", "modis_points.parquet").exists(), "| meta:", c.path("interim", "modis_points.meta.json").exists())
try:
    modis.load_modis_points(c); print("(b) load accepted: BAD")
except FileNotFoundError as e:
    print("(b) load_modis_points refuses:", type(e).__name__)
