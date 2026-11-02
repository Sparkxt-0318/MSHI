"""Same-date Terra LST items: which item does each rule pick, and do the values differ?
(1) selection: HEAD plan_jobs (real function) vs the prototype's rule (modis_points_lst.py:63-66, verbatim
    logic: stable sort by datetime, setdefault per (year, month)), for several fake 'API orders';
(2) values: the UNMODIFIED handoff script (runpy, fake STAC + fake token; no network) vs HEAD extract_points
    on the same fake catalog, with and without ties, API order 'desc' (datetime desc, id desc).
usage: ties.py WORKDIR"""
import os, runpy, sys, types
W = sys.argv[1]
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/verify-fidelity2/fake")
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
import fakepc2
from mshi.config import load_config
from mshi.data import modis

m = load_config()["sources"]["modis"]
pts = pd.DataFrame({"lat": [p[0] for p in fakepc2.PTS], "lon": [p[1] for p in fakepc2.PTS]})
pts["site_key"] = modis.site_key(pts.lat, pts.lon, 5).values
pts["h"], pts["v"] = modis.sinusoidal_tiles(pts.lon.values, pts.lat.values, m)
TILES = f"{W}/tiles"


def proto_firsts(cat, h, v):
    """The prototype's rule (modis_points_lst.py:37-40, 63-66)."""
    q = {"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}
    its = [i for i in cat.search(collections=["modis-11A2-061"], datetime="2020-01-01/2024-12-31", query=q,
                                 max_items=500).item_collection() if i.id.startswith("MOD11A2")]
    firsts = {}
    for it in sorted(its, key=lambda i: modis.item_datetime(i)):
        firsts.setdefault((modis.item_datetime(it).year, modis.item_datetime(it).month), it)
    return {k: it.id for k, it in firsts.items()}


print("== (1) selection of the first LST composite per month")
for ties in (False, True):
    for order in ("desc", "asc", "date_desc_id_asc", "shuffle"):
        cat = fakepc2.FakeCatalog(TILES, ties=ties, order=order)
        h, v = cat.tile
        jobs = modis.plan_jobs(pts, m, cat, kinds=("lst",))
        v3 = {}
        for kind, href, _sub, when in jobs:
            if kind == "lst_day":
                v3[(when.year, when.month)] = os.path.basename(href).rsplit(".LST_Day_1km.tif", 1)[0]
        pr = proto_firsts(cat, h, v)
        diff = sorted(k for k in pr if pr[k] != v3.get(k))
        ex = f"; e.g. {diff[0]}: v3 {v3[diff[0]][-13:]} vs prototype {pr[diff[0]][-13:]}" if diff else ""
        print(f"ties={ties!s:5} API order={order:16} months={len(v3)} differing picks={len(diff)} {diff}{ex}")

print("== (2) values: unmodified handoff script vs HEAD extract_points (fake STAC/token, local rasters)")
import requests
requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda: {"token": "tok"}, raise_for_status=lambda: None)
sites_csv = f"{W}/sites.csv"
pts[["site_key", "lat", "lon"]].to_csv(sites_csv, index=False)
for ties in (False, True):
    mod = types.ModuleType("pystac_client")
    mod.Client = types.SimpleNamespace(open=lambda url, **k: fakepc2.FakeCatalog(TILES, ties=ties, order="desc"))
    sys.modules["pystac_client"] = mod
    out = f"{W}/proto_ties{int(ties)}.parquet"
    sys.argv = ["modis_points_lst.py", sites_csv, out]
    runpy.run_path("/home/user/MSHI/docs/handoff/scripts/modis_points_lst.py", run_name="__main__")
    proto = pd.read_parquet(out).set_index("site_key")
    port, info = modis.extract_points(pts[["site_key", "lat", "lon"]], m, catalog=fakepc2.FakeCatalog(TILES, ties=ties, order="desc"),
                                      tokens=fakepc2.FakeTokens())
    port = port.set_index("site_key").loc[proto.index]
    for c in ["npp", "lst_day", "lst_night", "npp_n", "lst_day_n", "lst_night_n"]:
        d = (port[c].astype(float) - proto[c].astype(float)).abs()
        print(f"ties={ties!s:5} {c:12} max|v3 - prototype| = {d.max():.3g}   sites differing > 1e-12: {(d > 1e-12).sum()}/{len(d)}")
