"""MODIS stage re-check: the real modis_points -> extract_points -> plan_jobs -> _read_job -> read_windows ->
aggregate -> write_modis_cache / load_modis_points of a package copy (default pkg/head), in a smoke sandbox
(out_root and paths.raw in scratch). Faked: pystac_client (fakepc3.FakeCatalog), the SAS token (TokenCache),
mshi.netutil.check_reachable. Site tables + build_sites.json are written into the sandbox (stand-in for
build_sites, as tests/test_robustness.py fake_build does).
usage: stage.py WORKDIR SCENARIO [PKG]"""
import copy, hashlib, json, os, shutil, sys, types
SCR = "fixcheck3_scripts/modis-rasters"
W, SC = sys.argv[1], sys.argv[2]
PKG = sys.argv[3] if len(sys.argv) > 3 else "head"
sys.path.insert(0, f"{SCR}/fake")
sys.path.insert(0, f"{SCR}/pkg/{PKG}")
import numpy as np, pandas as pd
import fakepc3
import mshi
from mshi.config import Config, load_config
from mshi.io import write_result, write_table, read_json, require_outputs
import mshi.netutil as N
from mshi.data import modis
assert mshi.__file__.startswith(f"{SCR}/pkg/{PKG}/"), mshi.__file__

meta = pd.read_csv(f"{W}/sites_meta.csv")
TILES3 = sorted({(int(h), int(v)) for h, v, k in zip(meta.h, meta.v, meta.kind) if k != "tile4"})
T0 = TILES3[0]
t0 = f"h{T0[0]:02d}v{T0[1]:02d}"
ROOT = f"{W}/tiles"
STATE = {"cat_kw": {}, "catalogs": [], "reach": []}


class FakeClient:
    @staticmethod
    def open(url, **kw):
        c = fakepc3.FakeCatalog(ROOT, TILES3, **STATE["cat_kw"])
        STATE["catalogs"].append(c)
        return c


mod = types.ModuleType("pystac_client")
mod.Client = FakeClient
sys.modules["pystac_client"] = mod
modis.TokenCache = fakepc3.FakeTokens
N.check_reachable = lambda url, *a, **k: STATE["reach"].append(url)
reads = []
_real_rw = modis.read_windows


def rw(href, sub, kind, m):
    reads.append(href)
    return _real_rw(href, sub, kind, m)


modis.read_windows = rw
base = load_config()


def sandbox(name, edit=None, csv="sites3.csv"):
    d = copy.deepcopy(base.data)
    d["paths"]["raw"] = f"{W}/sb/{name}/raw"
    if edit:
        edit(d)
    c = Config(d, source=base.source, out_root=f"{W}/sb/{name}/out")
    pts = pd.read_csv(f"{W}/{csv}")
    st = pd.DataFrame({"site_id": [f"s{i}" for i in range(len(pts))], "lat": pts.lat, "lon": pts.lon,
                       "continent": "Europe", "log_rs": 6.0})
    outs = [write_table(st, c.path("derived", f"sites_v3_{t}.parquet")) for t in ("qc", "repo")]
    write_result(c, {"fake": True}, "build_sites.json", outputs=outs)
    return c


def run(c, **cat_kw):
    STATE["cat_kw"] = cat_kw
    n0 = len(reads)
    try:
        r = modis.modis_points(c)
        status = "ok"
    except Exception as e:  # noqa: BLE001
        r, status = None, f"{type(e).__name__}: {str(e)[:300]}"
    rec = read_json(c.path("results", "modis_points.json")) if c.path("results", "modis_points.json").exists() else None
    pq = c.path("interim", "modis_points.parquet")
    return {"status": status, "cached": bool(r and r.get("cached")), "reads": len(reads) - n0,
            "rec_status": rec.get("status") if rec else None,
            "n_raster_reads": rec.get("n_raster_reads") if rec else None,
            "n_failed_reads": rec.get("n_failed_reads") if rec else None,
            "catalog_gaps": (rec.get("catalog_gaps") or [])[:8] if rec else None,
            "n_catalog_gaps": rec.get("n_catalog_gaps") if rec else None,
            "ties": rec.get("lst_same_date_ties") if rec else None,
            "parquet": hashlib.sha256(pq.read_bytes()).hexdigest()[:12] if pq.exists() else None}


def load(c, keys=None):
    try:
        return modis.load_modis_points(c, keys)
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:200]}"


def drop_ids(prefixes):
    return lambda it: any(it.id.startswith(p) for p in prefixes)


out = {}
if SC == "complete":
    c = sandbox("complete")
    out["run1"] = run(c, order="shuffle")
    j1 = c.path("results", "modis_points.json").read_bytes()
    out["run2_cache"] = run(c, order="shuffle")
    out["json_identical_on_cache_hit"] = c.path("results", "modis_points.json").read_bytes() == j1
    st = pd.read_parquet(c.path("interim", "modis_points.parquet"))
    ref = pd.read_parquet(f"{W}/port_clip_shuffle.parquet")
    out["stage_table_equals_extract_points_table"] = bool(st.equals(ref))
    pr = pd.read_parquet(f"{W}/proto_clip_shuffle.parquet")
    out["stage_vs_proto_max_rel"] = {k: float(np.nanmax(np.abs(st[k] - pr[k]) / np.abs(pr[k]))) for k in ["npp", "lst_day", "lst_night"]}
    out["load_ok"] = isinstance(load(c, set(st.site_key)), pd.DataFrame)
    out["searches"] = sorted(set((x[0], x[1], x[4]) for cc in STATE["catalogs"] for x in cc.calls))
    out["probes"] = sorted(set(STATE["reach"]))
    # determinism across API orders: delete the cache, re-extract with 'desc' and 'asc'
    for order in ("desc", "asc"):
        c2 = sandbox(f"complete_{order}")
        out[f"run_{order}"] = run(c2, order=order)
elif SC == "missing_first_composite":
    # tile 0 lacks the Terra composite of 2021-01-01 (first of Jan 2021) and of 2023-04-07 (first of Apr 2023)
    c = sandbox("missing_first")
    out["run"] = run(c, order="shuffle", drop=drop_ids([f"MOD11A2.A2021001.{t0}", f"MOD11A2.A2023097.{t0}"]))
    ref = pd.read_parquet(f"{W}/port_clip_shuffle.parquet").set_index("site_key")
    got = load(c)
    if isinstance(got, pd.DataFrame):
        got = got.set_index("site_key").loc[ref.index]
        d = (got.lst_day - ref.lst_day).abs()
        out["accepted_by_load_modis_points"] = True
        out["lst_day_max_abs_change_vs_complete_catalog"] = float(d.max())
        out["sites_changed"] = int((d > 1e-9).sum())
        out["lst_day_n_change"] = sorted(set((got.lst_day_n - ref.lst_day_n).tolist()))
    else:
        out["load"] = got
elif SC == "missing_month":
    c = sandbox("missing_month")
    out["run"] = run(c, order="shuffle", drop=drop_ids([f"MOD11A2.A2022{d:03d}.{t0}" for d in (121, 129, 137, 145)]))
    out["parquet_exists"] = c.path("interim", "modis_points.parquet").exists()
elif SC == "npp_terra_missing_aqua_present":
    c = sandbox("npp_missing")
    out["run"] = run(c, order="shuffle", drop=drop_ids([f"MOD17A3HGF.A2023001.{t0}"]))
elif SC == "lst_year_aqua_only":
    c = sandbox("aqua_only")
    out["run"] = run(c, order="shuffle", drop=drop_ids([f"MOD11A2.A2022"]))
elif SC == "truncation":
    c = sandbox("trunc6y", edit=lambda d: d["sources"]["modis"].__setitem__("datetime", "2019-01-01/2024-12-31"))
    out["six_year_range"] = run(c, order="shuffle")
    c = sandbox("trunc_eq", edit=lambda d: d["sources"]["modis"].__setitem__("max_items_per_tile", 460))
    out["max_items_460_clip"] = run(c, order="shuffle")
    c = sandbox("trunc_ov")
    out["max_items_500_overlap"] = run(c, order="shuffle", end_mode="overlap")
    # how many items the configured 5-year search returns per tile (Terra + Aqua), clip and overlap
    for em in ("clip", "overlap"):
        cat = fakepc3.FakeCatalog(ROOT, TILES3, end_mode=em)
        q = {"modis:horizontal-tile": {"eq": T0[0]}, "modis:vertical-tile": {"eq": T0[1]}}
        out[f"n_items_lst_{em}"] = len(cat.search(["modis-11A2-061"], "2020-01-01/2024-12-31", q, None).item_collection())
        out[f"n_items_npp_{em}"] = len(cat.search(["modis-17A3HGF-061"], "2020-01-01/2024-12-31", q, None).item_collection())
elif SC == "ties":
    ties = {T0: [(2021, 1, "2099001000000"), (2022, 153, "2000001000000")]}
    pm = meta[meta.kind != "tile4"]
    out["tie_rasters_written"] = fakepc3.write_rasters(fakepc3.FakeCatalog(ROOT, TILES3, ties=ties), pm)
    res = {}
    for order in ("shuffle", "desc", "asc"):
        c = sandbox(f"ties_{order}")
        res[order] = run(c, order=order, ties=ties)
    out["runs"] = res
    out["same_parquet_all_orders"] = len({r["parquet"] for r in res.values()}) == 1
    c = sandbox("ties_shuffle")
    st = pd.read_parquet(c.path("interim", "modis_points.parquet"))
    ref = pd.read_parquet(f"{W}/port_clip_shuffle.parquet")
    out["sites_lst_changed_vs_no_ties"] = int(((st.lst_day - ref.lst_day).abs() > 1e-9).sum())
elif SC == "empty_tile":
    c = sandbox("empty_tile", csv="sites.csv")
    out["run"] = run(c, order="shuffle")
    gaps = read_json(c.path("results", "modis_points.json"))
    out["n_catalog_gaps"] = gaps.get("n_catalog_gaps")
    acc = list(gaps.get("catalog_gaps") or [])
    c2 = sandbox("empty_tile_acc", csv="sites.csv",
                 edit=lambda d: d["sources"]["modis"].__setitem__("accepted_catalog_gaps", acc))
    out["run_with_65_accepted"] = run(c2, order="shuffle")
elif SC == "failed_read":
    # a tie item with a SMALLER id is chosen for Jan 2023 in tile 0, but its COG does not exist (unreadable);
    # a leftover max_failed_reads: 5 in the config must not act as a tolerance any more
    ties = {T0: [(2023, 1, "2000000000000")]}
    c = sandbox("failed_read", edit=lambda d: d["sources"]["modis"].__setitem__("max_failed_reads", 5))
    out["run"] = run(c, order="shuffle", ties=ties)
    out["parquet_exists"] = c.path("interim", "modis_points.parquet").exists()
    out["meta_exists"] = c.path("interim", "modis_points.meta.json").exists()
    out["load"] = load(c) if not out["parquet_exists"] else "parquet present"
    rec = read_json(c.path("results", "modis_points.json"))
    out["failed_reads"] = [f.split("/")[-1][:120] for f in rec.get("failed_reads", [])]
elif SC == "many_gaps":
    # Terra LST missing for 2020-2022 in all 3 tiles: 108 gaps; accept exactly what the record lists, re-run
    c = sandbox("many_gaps")
    drop = drop_ids(["MOD11A2.A2020", "MOD11A2.A2021", "MOD11A2.A2022"])
    out["run1"] = run(c, order="shuffle", drop=drop)
    rec = read_json(c.path("results", "modis_points.json"))
    listed = list(rec["catalog_gaps"])
    out["n_catalog_gaps"], out["n_listed_in_record"] = rec["n_catalog_gaps"], len(listed)
    c2 = sandbox("many_gaps2", edit=lambda d: d["sources"]["modis"].__setitem__("accepted_catalog_gaps", listed))
    out["run2_after_accepting_the_listed_gaps"] = run(c2, order="shuffle", drop=drop)
elif SC == "missing_first_then_recovered":
    c = sandbox("missing_first_rec")
    drop = drop_ids([f"MOD11A2.A2021001.{t0}", f"MOD11A2.A2023097.{t0}"])
    out["run_short_catalog"] = run(c, order="shuffle", drop=drop)
    out["run_catalog_recovered"] = run(c, order="shuffle")          # complete catalog again, same config
    ref = pd.read_parquet(f"{W}/port_clip_shuffle.parquet").set_index("site_key")
    got = load(c).set_index("site_key").loc[ref.index]
    out["lst_day_still_differs_from_complete_catalog_at_sites"] = int(((got.lst_day - ref.lst_day).abs() > 1e-9).sum())
    out["max_abs_diff"] = float((got.lst_day - ref.lst_day).abs().max())
elif SC == "overlap":
    c = sandbox("overlap")
    out["run"] = run(c, order="shuffle", end_mode="overlap")
    st = pd.read_parquet(c.path("interim", "modis_points.parquet"))
    out["lst_day_n_range"] = [int(st.lst_day_n.min()), int(st.lst_day_n.max())]
print(json.dumps(out, indent=1, default=str))
