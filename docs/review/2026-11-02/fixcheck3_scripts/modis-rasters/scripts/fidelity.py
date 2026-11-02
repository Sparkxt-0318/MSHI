"""Fidelity: the UNMODIFIED handoff prototype docs/handoff/scripts/modis_points_lst.py (runpy; fake pystac_client
and fake token via requests.get; no network) vs HEAD extract_points (archive copy pkg/head == a6c00bc mshi/)
on the same fake STAC catalog (complete 2020-2024, Terra + Aqua, datetime None items, STAC datetime
intersection, max_items truncation) and the same synthetic sinusoidal GeoTIFFs.
usage: fidelity.py WORKDIR SCENARIO   (scenario: clip_shuffle | clip_desc | overlap_shuffle | ties_shuffle | ties_desc | ties_asc)
Writes WORKDIR/proto_<sc>.parquet, port_<sc>.parquet, cmp_<sc>.json."""
import json, os, runpy, sys, types
SCR = "fixcheck3_scripts/modis-rasters"
sys.path.insert(0, f"{SCR}/fake")
sys.path.insert(0, f"{SCR}/pkg/head")
import numpy as np, pandas as pd
import fakepc3
import mshi
from mshi.config import load_config
from mshi.data import modis
assert mshi.__file__.startswith(f"{SCR}/pkg/head/")

W, SC = sys.argv[1], sys.argv[2]
end_mode = "overlap" if SC.startswith("overlap") else "clip"
order = SC.split("_")[1]
meta = pd.read_csv(f"{W}/sites_meta.csv")
TILES = sorted({(int(h), int(v)) for h, v, k in zip(meta.h, meta.v, meta.kind) if k != "tile4"})
ties = {}
if SC.startswith("ties"):
    # tile 0: Jan-2021 first composite gets a reprocessed twin with a LARGER id, Jun-2022 one with a SMALLER id
    t0 = TILES[0]
    ties = {t0: [(2021, 1, "2099001000000"), (2022, 153, "2000001000000")]}
ROOT = f"{W}/tiles"
m = load_config()["sources"]["modis"]

pts = pd.read_csv(f"{W}/sites3.csv")                      # same parser as the prototype
pm = pts.merge(meta[["site_key", "h", "v", "kind"]], on="site_key")
fill = pm[pm.kind == "site"].iloc[0]


def make_cat():
    return fakepc3.FakeCatalog(ROOT, TILES, order=order, end_mode=end_mode, ties=ties)


nfiles = fakepc3.write_rasters(make_cat(), pm, fill_point=fill)

# ---------------- prototype (unmodified), in this process
import requests
requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda: {"token": "tok"}, raise_for_status=lambda: None)
proto_cats = []


class FakeClient:
    @staticmethod
    def open(url, **kw):
        assert url == "https://planetarycomputer.microsoft.com/api/stac/v1", url
        c = make_cat()
        proto_cats.append(c)
        return c


mod = types.ModuleType("pystac_client")
mod.Client = FakeClient
sys.modules["pystac_client"] = mod
out_proto = f"{W}/proto_{SC}.parquet"
sys.argv = ["modis_points_lst.py", f"{W}/sites3.csv", out_proto]
G = runpy.run_path("/home/user/MSHI/docs/handoff/scripts/modis_points_lst.py", run_name="__main__")
proto = pd.read_parquet(out_proto)
proto_jobs = sorted((j[0], j[2], tuple(sorted(j[3].site_key))) for j in G["jobs"])
acc = G["acc"]

# ---------------- port (HEAD extract_points), same catalog, read_windows wrapped to record per-raster values
real_rw = modis.read_windows
rec = []


def rw(href, sub, kind, mm):
    out = real_rw(href, sub, kind, mm)
    rec.append((kind, href.split("?")[0], out))
    return out


modis.read_windows = rw
cat = make_cat()
port, info = modis.extract_points(pts[["site_key", "lat", "lon"]], m, catalog=cat, tokens=fakepc3.FakeTokens())
modis.read_windows = real_rw
port.to_parquet(f"{W}/port_{SC}.parquet", index=False)
jobs = modis.plan_jobs(pd.concat([pts, pd.DataFrame(dict(zip(["h", "v"], modis.sinusoidal_tiles(pts.lon.values, pts.lat.values, m))))], axis=1),
                       m, make_cat())
port_jobs = sorted((j[0], j[1], tuple(sorted(j[2].site_key))) for j in jobs)

# ---------------- compare
res = {"scenario": SC, "files_written_now": nfiles, "n_points": len(pts), "tiles": TILES,
       "search_params_proto": sorted(set((c[0], c[1], c[4]) for cc in proto_cats for c in cc.calls)),
       "search_params_port": sorted(set((c[0], c[1], c[4]) for c in cat.calls)),
       "n_jobs_proto": len(proto_jobs), "n_jobs_port": len(port_jobs), "job_multisets_equal": proto_jobs == port_jobs,
       "info": {k: (v if not isinstance(v, list) else v[:6]) for k, v in info.items() if k != "failed_reads"},
       "n_failed_reads": len(info["failed_reads"])}
res["lst_first_composites_per_tile"] = {t: sorted(j[1].split("/")[-1].split(".")[1] for j in port_jobs
                                                  if j[0] == "lst_day" and f".{t}." in j[1])[:2] for t in
                                        sorted({j[1].split("/")[-1].split(".")[2] for j in port_jobs})}
res["lst_items_per_tile"] = {t: sum(1 for j in port_jobs if j[0] == "lst_day" and f".{t}." in j[1]) for t in
                             sorted({j[1].split("/")[-1].split(".")[2] for j in port_jobs})}
res["npp_items_per_tile"] = {t: sum(1 for j in port_jobs if j[0] == "npp" and f".{t}." in j[1]) for t in
                             sorted({j[1].split("/")[-1].split(".")[2] for j in port_jobs})}
# per-(site, kind) multisets of per-raster window means
port_acc = {}
for kind, href, vals in rec:
    for k, v in vals.items():
        port_acc.setdefault((k, kind), []).append(v)


def ms(lst):
    a = np.array(lst, float)
    return (int(np.isnan(a).sum()), sorted(a[~np.isnan(a)].tolist()))


keys = set(acc) | set(port_acc)
res["value_multisets_equal"] = all(ms(acc.get(k, [])) == ms(port_acc.get(k, [])) for k in keys)
res["n_site_kind_lists"] = len(keys)
P = port.set_index("site_key").loc[proto.site_key].reset_index()
res["row_order_equal"] = list(proto.site_key) == list(port.site_key)
res["columns_proto"], res["columns_port"] = list(proto.columns), list(port.columns)
res["dtypes_equal"] = {c: str(proto[c].dtype) == str(P[c].dtype) for c in proto.columns}
cols = {}
for c in ["npp", "lst_day", "lst_night"]:
    x, y = proto[c].to_numpy(float), P[c].to_numpy(float)
    f = ~np.isnan(x) & ~np.isnan(y)
    d = np.abs(x[f] - y[f])
    rel = d / np.abs(x[f]).clip(1e-300)
    cols[c] = {"nan_pattern_equal": bool((np.isnan(x) == np.isnan(y)).all()), "n_nan": int(np.isnan(x).sum()),
               "finite": int(f.sum()), "bit_identical": int((x[f] == y[f]).sum()),
               "max_abs_diff": float(d.max()) if d.size else 0.0, "max_rel_diff": float(rel.max()) if rel.size else 0.0,
               "n_equal": bool((proto[c + "_n"].to_numpy() == P[c + "_n"].to_numpy()).all()),
               "n_range": [int(proto[c + "_n"].min()), int(proto[c + "_n"].max())]}
res["columns"] = cols
print(json.dumps(res, indent=1, default=str))
json.dump(res, open(f"{W}/cmp_{SC}.json", "w"), indent=1, default=str)
