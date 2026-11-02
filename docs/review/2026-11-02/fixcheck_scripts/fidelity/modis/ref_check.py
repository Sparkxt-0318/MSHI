"""Reference check: run the prototype's own module-level job planning and read_windows (exec'd from the
unmodified script, up to its thread pool), compare its job list with the port's plan_jobs, and check that
(a) the port's means == nanmean of the per-raster values in sorted (kind, date, href) order, bit for bit;
(b) the prototype's means lie within the spread of nanmean over random orders of the same values."""
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd, requests
import fakepc
from mshi.config import load_config
from mshi.data import modis

ARGS = list(sys.argv)
ties = len(ARGS) > 3 and ARGS[3] == "ties"
tiles = eval(open(os.path.join(HERE, "tiles.txt")).read())
requests.get = lambda url, timeout=None, **k: types.SimpleNamespace(json=lambda: {"token": "tok"})
fakepc.FakeClient.tiles, fakepc.FakeClient.ties = tiles, ties
mod = types.ModuleType("pystac_client"); mod.Client = fakepc.FakeClient; sys.modules["pystac_client"] = mod
src = open(os.path.join(HERE, "proto_modis_points_lst.py")).read()
head = src.split("\nacc = {}\n")[0]                     # everything before the thread pool
ns = {"__name__": "proto"}
sys.argv = ["proto", os.path.join(HERE, "sites.csv"), "/dev/null"]
exec(compile(head, "proto_modis_points_lst.py", "exec"), ns)
pjobs = ns["jobs"]                                       # (kind, col, href, sub, year)
m = load_config()["sources"]["modis"]
pts = pd.read_csv(os.path.join(HERE, "sites.csv"))
pts["h"], pts["v"] = modis.sinusoidal_tiles(pts.lon.values, pts.lat.values, m)
qjobs = modis.plan_jobs(pts, m, fakepc.FakeCatalog(tiles, ties))   # (kind, href, sub, when)
ps = sorted((j[0], j[2], tuple(j[3].site_key)) for j in pjobs)
qs = sorted((j[0], j[1], tuple(j[2].site_key)) for j in qjobs)
print(f"jobs: prototype {len(ps)}, port {len(qs)}, identical (kind, href, points) multisets: {ps == qs}")
if ps != qs:
    print("  only prototype:", sorted(set(ps) - set(qs))[:6]); print("  only port:", sorted(set(qs) - set(ps))[:6])
# per-raster values with the PROTOTYPE's read_windows, keyed by the port's job tuple (for its sort key)
per = []
for kind, href, sub, when in qjobs:
    vals = ns["read_windows"](href + "?tok", sub, "npp" if kind == "npp" else "lst")
    q = modis.read_windows(href + "?tok", sub, kind, m)
    assert vals.keys() == q.keys() and all((vals[k] == q[k]) or (np.isnan(vals[k]) and np.isnan(q[k])) for k in vals), href
    per.append((kind, when, href, vals))
print("prototype read_windows == port read_windows on all", len(per), "rasters: True")
proto = pd.read_parquet(ARGS[1]).set_index("site_key")
port = pd.read_parquet(ARGS[2]).set_index("site_key")
rng = np.random.default_rng(0)
bad_sorted = bad_range = 0
for kind in ["npp", "lst_day", "lst_night"]:
    for k in pts.site_key:
        rows = sorted([r for r in per if r[0] == kind and k in r[3]], key=lambda r: (r[0], str(r[1]), r[2]))
        v = np.array([r[3][k] for r in rows], float)
        ref = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
        got = port.loc[k, kind]
        if not ((np.isnan(ref) and np.isnan(got)) or ref == got):
            bad_sorted += 1
        if np.isfinite(v).any():
            perms = [np.nanmean(v[rng.permutation(len(v))]) for _ in range(300)] + [ref]
            pv = proto.loc[k, kind]
            if not (min(perms) - 1e-300 <= pv <= max(perms) + 1e-300):
                bad_range += 1
                print("  outside permutation range:", kind, k, pv, min(perms), max(perms))
print(f"port != sorted-order nanmean: {bad_sorted}; prototype outside the range of order permutations: {bad_range}")
