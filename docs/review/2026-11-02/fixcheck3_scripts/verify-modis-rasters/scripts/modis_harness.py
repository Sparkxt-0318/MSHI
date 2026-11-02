"""Verifier's own MODIS harness (independent of the reviewer's fakepc3/stage.py).

Runs the REAL mshi.data.modis.modis_points -> extract_points -> plan_jobs -> _read_job -> read_windows ->
aggregate -> write_modis_cache / load_modis_points of a package copy (git archive HEAD in scratch), in a smoke
sandbox (out_root and paths.raw in scratch). Faked: the pystac_client module (STAC search with the STAC
interval-intersection rule and pystac_client 0.9.1's own datetime expansion), the SAS token, and
mshi.netutil.check_reachable. read_windows is the real function; a wrapper creates the item's small synthetic
sinusoidal GeoTIFF on first use (seeded by the asset name) and strips the '?tok' query.

usage: modis_harness.py SCENARIO
"""
import copy
import hashlib
import json
import os
import random
import sys
import types
from datetime import datetime, timedelta, timezone

V = "fixcheck3_scripts/verify-modis-rasters"
PKG = os.environ.get("PKG", "head")
sys.path.insert(0, f"{V}/pkg/{PKG}")
import numpy as np
import pandas as pd
from pystac_client.item_search import ItemSearch as _RealItemSearch   # real class, for the datetime expansion

import mshi
import mshi.netutil as N
from mshi.config import Config, load_config
from mshi.data import modis
from mshi.io import read_json, write_result, write_table
assert mshi.__file__.startswith(f"{V}/pkg/{PKG}/"), mshi.__file__

SC = sys.argv[1]
WORK = f"{V}/work/modis"
TIF = f"{WORK}/tifs"
UTC = timezone.utc
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
R_E, T_TILE, X0, Y0 = 6371007.181, 1111950.5197, -20015109.354, 10007554.677

SITES = pd.DataFrame({"lat": [48.0, 48.3, 47.5, 45.2, 46.1, 45.3, 40.0, 41.0, 40.5],
                      "lon": [10.0, 11.2, 9.1, 14.0, 25.0, 27.5, -100.0, -98.5, -101.2]})
BASE = load_config()
M = BASE["sources"]["modis"]
SITES["h"], SITES["v"] = modis.sinusoidal_tiles(SITES.lon.values, SITES.lat.values, M)
TILES = sorted({(int(h), int(v)) for h, v in zip(SITES.h, SITES.v)})


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def P(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def item(iid, start, end, assets, tile, dt_none):
    return types.SimpleNamespace(
        id=iid, datetime=None if dt_none else start,
        properties={"start_datetime": iso(start), "end_datetime": iso(end)},
        assets={a: types.SimpleNamespace(href=f"{TIF}/{tile}/{iid}.{a}.tif") for a in assets},
        _s=start, _e=end)


def tile_items(h, v, end_mode):
    t = f"h{h:02d}v{v:02d}"
    npp, lst = [], []
    for y in range(2015, 2026):
        s, e = datetime(y, 1, 1, tzinfo=UTC), datetime(y, 12, 31, 23, 59, 59, tzinfo=UTC)
        for pre in ("MOD17A3HGF", "MYD17A3HGF"):
            npp.append(item(f"{pre}.A{y}001.{t}.061.X", s, e, ["Npp_500m"], t, pre == "MOD17A3HGF" and y % 2))
        for doy in range(1, 366, 8):
            s = datetime(y, 1, 1, tzinfo=UTC) + timedelta(days=doy - 1)
            e = s + timedelta(days=8, seconds=-1)
            if end_mode == "clip":
                e = min(e, datetime(y, 12, 31, 23, 59, 59, tzinfo=UTC))
            for pre in ("MOD11A2", "MYD11A2"):
                lst.append(item(f"{pre}.A{y}{doy:03d}.{t}.061.X", s, e, ["LST_Day_1km", "LST_Night_1km"], t,
                                pre == "MOD11A2" and doy % 3 == 0))
    return npp, lst


class FakeCatalog:
    def __init__(self, end_mode="clip", drop=lambda iid: False, seed=0):
        self.end_mode, self.drop, self.seed, self.calls = end_mode, drop, seed, 0

    def search(self, collections, datetime=None, query=None, max_items=None, **kw):
        self.calls += 1
        h, v = int(query["modis:horizontal-tile"]["eq"]), int(query["modis:vertical-tile"]["eq"])
        q0, q1 = (P(x) for x in _RealItemSearch.__new__(_RealItemSearch)._format_datetime(datetime).split("/"))
        npp, lst = tile_items(h, v, self.end_mode) if (h, v) in TILES else ([], [])
        its = npp if collections[0] == M["npp"]["collection"] else lst
        its = [i for i in its if i._s <= q1 and i._e >= q0 and not self.drop(i.id)]   # STAC: interval intersects
        random.Random(f"{self.seed}{h}{v}{collections[0]}").shuffle(its)            # arbitrary API order
        if max_items is not None:
            its = its[:max_items]
        return types.SimpleNamespace(item_collection=lambda: list(its))


STATE = {"catalog_kw": {}}
fake_pc = types.ModuleType("pystac_client")
fake_pc.Client = types.SimpleNamespace(open=lambda url, **kw: FakeCatalog(**STATE["catalog_kw"]))
sys.modules["pystac_client"] = fake_pc


class Tokens:
    def __init__(self, *a, **k):
        pass

    def get(self, force=False):
        return "tok"


modis.TokenCache = Tokens
N.check_reachable = lambda *a, **k: None
READS = []
_real_read_windows = modis.read_windows


def make_tif(path):
    import rasterio
    from rasterio.transform import from_origin
    tile = path.split("/")[-2]
    h, v = int(tile[1:3]), int(tile[4:6])
    sub = SITES[(SITES.h == h) & (SITES.v == v)]
    px = T_TILE / 2400 if "Npp" in path else T_TILE / 1200
    xs = R_E * np.radians(sub.lon.values) * np.cos(np.radians(sub.lat.values))
    ys = R_E * np.radians(sub.lat.values)
    x0, y1 = xs.min() - 20e3, ys.max() + 20e3
    W = int((xs.max() - xs.min() + 40e3) / px) + 1
    H = int((ys.max() - ys.min() + 40e3) / px) + 1
    rng = np.random.default_rng(int(hashlib.sha256(path.split("/")[-1].encode()).hexdigest()[:12], 16))
    if "Npp" in path:
        arr, dt = rng.integers(500, 12000, (H, W)), "int16"
    else:
        lvl = rng.integers(13500, 15500)                      # item-level offset: composites differ
        arr, dt = lvl + rng.integers(-200, 200, (H, W)), "uint16"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rasterio.open(path + ".tmp.tif", "w", driver="GTiff", width=W, height=H, count=1, dtype=dt,
                       transform=from_origin(x0, y1, px, px), crs=SIN) as dst:
        dst.write(arr.astype(dt), 1)
    os.replace(path + ".tmp.tif", path)


def read_windows(href, sub, kind, m):
    path = href.split("?")[0]
    READS.append(path)
    if not os.path.exists(path):
        make_tif(path)
    return _real_read_windows(path, sub, kind, m)


modis.read_windows = read_windows


def sandbox(name, edit=None):
    d = copy.deepcopy(BASE.data)
    d["paths"]["raw"] = f"{WORK}/sb/{name}/raw"
    if edit:
        edit(d)
    c = Config(d, source=BASE.source, out_root=f"{WORK}/sb/{name}/out")
    st = pd.DataFrame({"site_id": [f"s{i}" for i in range(len(SITES))], "lat": SITES.lat, "lon": SITES.lon,
                       "continent": "Europe", "log_rs": 6.0})
    outs = [write_table(st, c.path("derived", f"sites_v3_{t}.parquet")) for t in ("qc", "repo")]
    write_result(c, {"fake": True}, "build_sites.json", outputs=outs)
    return c


def run(c, **catalog_kw):
    STATE["catalog_kw"] = catalog_kw
    n0 = len(READS)
    try:
        r = modis.modis_points(c)
        status = "ok"
    except Exception as e:  # noqa: BLE001
        r, status = None, f"{type(e).__name__}: {str(e)[:260]}"
    rp = c.path("results", "modis_points.json")
    rec = read_json(rp) if rp.exists() else {}
    pq = c.path("interim", "modis_points.parquet")
    return {"status": status, "cached": bool(r and r.get("cached")), "actual_reads": len(READS) - n0,
            "rec.status": rec.get("status"), "rec.n_raster_reads": rec.get("n_raster_reads"),
            "rec.n_failed_reads": rec.get("n_failed_reads"), "rec.n_catalog_gaps": rec.get("n_catalog_gaps"),
            "rec.len(catalog_gaps)": len(rec.get("catalog_gaps") or []),
            "rec.catalog_gaps[:4]": (rec.get("catalog_gaps") or [])[:4],
            "rec.lst_same_date_ties": rec.get("lst_same_date_ties"),
            "parquet_sha12": hashlib.sha256(pq.read_bytes()).hexdigest()[:12] if pq.exists() else None}


def load(c):
    try:
        return modis.load_modis_points(c, list(modis.site_key(SITES.lat, SITES.lon)))
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:200]}"


def reference():
    """Table from a complete 'clip' catalog (computed once, in its own sandbox)."""
    c = sandbox("ref_complete")
    r = run(c)
    assert r["status"] == "ok", r
    return r, modis.load_modis_points(c).set_index("site_key")


def diff(got, ref):
    got = got.set_index("site_key").loc[ref.index]
    out = {}
    for k in ("npp", "lst_day", "lst_night"):
        d = (got[k] - ref[k]).abs()
        out[k] = {"sites_changed": int((d > 1e-9).sum()), "max_abs": float(d.max())}
        out[k + "_n"] = sorted(set(got[k + "_n"].astype(int).tolist()))
    tile_of = dict(zip(modis.site_key(SITES.lat, SITES.lon), (f"h{int(h):02d}v{int(v):02d}" for h, v in
                                                               zip(SITES.h, SITES.v))))
    d = (got.lst_day - ref.lst_day).abs()
    out["lst_day_changed_site_tiles"] = sorted({tile_of[k] for k in d.index[d > 1e-9]})
    return out


out = {"pkg": mshi.__file__, "tiles": [f"h{h:02d}v{v:02d}" for h, v in TILES], "n_sites": len(SITES)}
T0 = "h18v04"
if SC == "complete":
    r, ref = reference()
    out["run"] = r
    out["lst_day_n"] = sorted(set(ref.lst_day_n.tolist()))
    out["npp_n"] = sorted(set(ref.npp_n.tolist()))
elif SC == "missing_first":
    _, ref = reference()
    drop = {f"MOD11A2.A2021001.{T0}.061.X", f"MOD11A2.A2023097.{T0}.061.X"}
    c = sandbox("missing_first")
    out["run_short_catalog"] = run(c, drop=lambda i: i in drop)
    got = load(c)
    out["load_modis_points"] = "accepted" if isinstance(got, pd.DataFrame) else got
    if isinstance(got, pd.DataFrame):
        out["vs_complete"] = diff(got, ref)
    # catalog recovers (complete again), same config/code/points -> cache?
    out["run_catalog_recovered"] = run(c)
    got2 = load(c)
    out["after_recovery_vs_complete"] = diff(got2, ref)
    # what plan_jobs picked for those months
    pts = SITES.copy()
    pts["site_key"] = modis.site_key(pts.lat, pts.lon).values
    st = {}
    jobs = modis.plan_jobs(pts, M, FakeCatalog(drop=lambda i: i in drop), stats=st)
    pick = sorted({(j[3].strftime("%Y-%m-%d"), j[1].split("/")[-1].split(".061")[0]) for j in jobs
                   if j[0] == "lst_day" and T0 in j[1] and j[3].strftime("%Y-%m") in ("2021-01", "2023-04")})
    out["plan_jobs_choice_for_2021-01_2023-04"] = pick
    out["plan_jobs_stats"] = {k: len(v) for k, v in st.items()}
    # the gate features.verify_inputs applies to the MODIS table
    from mshi.io import require_outputs
    try:
        require_outputs(c, "modis_points.json", [c.path("interim", "modis_points.parquet")])
        out["require_outputs_modis_points.json"] = "accepted"
    except Exception as e:  # noqa: BLE001
        out["require_outputs_modis_points.json"] = f"{type(e).__name__}: {e}"
elif SC == "missing_month":
    c = sandbox("missing_month")
    drop = {f"MOD11A2.A2022{d:03d}.{T0}.061.X" for d in (121, 129, 137, 145)}
    out["run"] = run(c, drop=lambda i: i in drop)
    out["parquet_exists"] = c.path("interim", "modis_points.parquet").exists()
elif SC == "many_gaps":
    c = sandbox("many_gaps")
    drop = lambda i: i.startswith(("MOD11A2.A2020", "MOD11A2.A2021", "MOD11A2.A2022"))
    out["run1"] = run(c, drop=drop)
    rec = read_json(c.path("results", "modis_points.json"))
    listed = list(rec["catalog_gaps"])
    out["n_catalog_gaps"], out["n_listed"] = rec["n_catalog_gaps"], len(listed)
    c2 = sandbox("many_gaps_accepted", edit=lambda d: d["sources"]["modis"].__setitem__("accepted_catalog_gaps", listed))
    out["run2_after_accepting_listed"] = run(c2, drop=drop)
    rec2 = read_json(c2.path("results", "modis_points.json"))
    out["run2_gaps"] = rec2.get("catalog_gaps")
elif SC == "overlap":
    _, ref = reference()
    c = sandbox("overlap")
    out["run"] = run(c, end_mode="overlap")
    got = load(c)
    out["vs_complete_clip"] = diff(got, ref) if isinstance(got, pd.DataFrame) else got
    rec = read_json(c.path("results", "modis_points.json"))
    out["record_mentions_2019"] = "2019" in json.dumps({k: v for k, v in rec.items() if k != "cache_key"})
    pts = SITES.copy()
    pts["site_key"] = modis.site_key(pts.lat, pts.lon).values
    jobs = modis.plan_jobs(pts, M, FakeCatalog(end_mode="overlap"))
    out["jobs_dated_2019"] = sorted({(j[0], j[3].strftime("%Y-%m-%d"), j[1].split("/")[-1][:24]) for j in jobs
                                     if j[3].year == 2019})
    out["n_lst_day_jobs_per_tile"] = {t: sum(1 for j in jobs if j[0] == "lst_day" and t in j[1])
                                      for t in out["tiles"]}
print(json.dumps(out, indent=1, default=str))
