"""Run the full modis_points stage (sandbox out_root, fake STAC/token, real extraction code on the synthetic
GeoTIFFs), then the cache-hit path, then a replaced parquet with the sidecar left in place."""
import copy, json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
SB = os.path.join(HERE, "sandbox")
sys.path.insert(0, HERE); sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
import fakepc
from mshi.config import Config, load_config
import mshi.netutil as N
from mshi.data import modis

cfg = load_config()
data = copy.deepcopy(cfg.data)
data["paths"]["raw"] = os.path.join(SB, "raw")
sand = Config(data, source=cfg.source, out_root=os.path.join(SB, "out"))
pts = pd.read_csv(os.path.join(HERE, "sites.csv"))
modis.modis_point_set = lambda c: pts[["lat", "lon", "site_key"]].copy()
probes = []
N.check_reachable = lambda url, **k: probes.append(url)
fakepc.FakeClient.tiles = eval(open(os.path.join(HERE, "tiles.txt")).read())
mod = types.ModuleType("pystac_client"); mod.Client = fakepc.FakeClient; sys.modules["pystac_client"] = mod
modis.TokenCache = fakepc.FakeTokens

r1 = modis.modis_points(sand)
print("run 1:", {k: r1[k] for k in ["n_points", "n_raster_reads", "n_failed_reads", "missing"]}, "probes:", probes)
pq, meta = sand.path("interim", "modis_points.parquet"), sand.path("interim", "modis_points.meta.json")
j1 = sand.path("results", "modis_points.json").read_text()
got = modis.load_modis_points(sand, set(pts.site_key))
ref = pd.read_parquet(os.path.join(HERE, "out", "port_run1.parquet"))
print("stage table == extract_points table (exact):", got.equals(ref))
r2 = modis.modis_points(sand)
print("run 2 cached:", r2.get("cached"), "| results JSON unchanged:", sand.path("results", "modis_points.json").read_text() == j1,
      "| probes:", len(probes))
# a different table at the cached path, sidecar untouched (e.g. the handoff script or an older checkout
# writing data/interim/modis_points.parquet)
bad = got.copy(); bad["npp"] = bad["npp"] + 100.0; bad["npp_n"] = 1
bad.to_parquet(pq, index=False)
acc = modis.load_modis_points(sand, set(pts.site_key))
print("replaced parquet accepted by load_modis_points:", float((acc.npp - got.npp).abs().max()), "npp_n", sorted(set(acc.npp_n)))
r3 = modis.modis_points(sand)
print("run 3 after replacement: cached =", r3.get("cached"), "| re-extracted:", not r3.get("cached"))
