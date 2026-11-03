"""D-P2-6: adding the analysis sites to the MODIS point set must not change any value the locked test (or the NPP
check) uses. Point sets built from the real derived and allow-listed tables (read-only); the extraction is run with
the real plan_jobs / read_windows / aggregate on synthetic sinusoidal NPP rasters (one per tile, local GeoTIFFs)
and a fake STAC catalog, once for the Phase-1 point set (locked build + 889 original sites) and once for the
current one (+ analysis build); values at the common points are compared bit for bit."""
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config  # noqa: E402
from mshi.data import modis  # noqa: E402
from mshi.io import read_table  # noqa: E402

SCR = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb/modis")
SCR.mkdir(parents=True, exist_ok=True)
cfg = load_config()
m = dict(cfg["sources"]["modis"])
m["threads"] = 2
m["second_pass_threads"] = 1
nd = cfg["features"]["site_key_round"]


def point_set(with_analysis: bool) -> pd.DataFrame:
    frames = []
    for prefix in (("sites_v3", "sites_analysis") if with_analysis else ("sites_v3",)):
        for tag in cfg["site_build"]["variants"]:
            st = read_table(cfg, cfg.path("derived", f"{prefix}_{tag}.parquet"))
            frames.append(pd.DataFrame({"lat": st.lat.values, "lon": st.lon.values}))
    for rel in cfg["legacy_allowlist"]:
        o = read_table(cfg, cfg.repo_path(rel))
        frames.append(pd.DataFrame({"lat": o.latitude.values, "lon": o.longitude.values}))
    pts = pd.concat(frames, ignore_index=True)
    pts["site_key"] = modis.site_key(pts.lat, pts.lon, nd).values
    return pts.drop_duplicates("site_key").reset_index(drop=True)


new = modis.modis_point_set(cfg)                         # the code under review
assert new.equals(point_set(True)), "re-implementation differs from modis_point_set"
old = point_set(False)
print("points: Phase-1 set", len(old), "; current set", len(new), "; added", len(set(new.site_key) - set(old.site_key)),
      "; removed", len(set(old.site_key) - set(new.site_key)))
j = old.merge(new, on="site_key", suffixes=("_old", "_new"))
print("common keys:", len(j), "; coordinates identical for every common key:",
      bool(((j.lat_old == j.lat_new) & (j.lon_old == j.lon_new)).all()))
# keys that occur with several distinct coordinates across all input rows (rounding collisions)
frames = []
for prefix in ("sites_v3", "sites_analysis"):
    for tag in ("qc", "repo"):
        st = read_table(cfg, cfg.path("derived", f"{prefix}_{tag}.parquet"))
        frames.append(pd.DataFrame({"lat": st.lat.values, "lon": st.lon.values, "src": f"{prefix}_{tag}"}))
for rel in cfg["legacy_allowlist"]:
    o = read_table(cfg, cfg.repo_path(rel))
    frames.append(pd.DataFrame({"lat": o.latitude.values, "lon": o.longitude.values, "src": "legacy"}))
allp = pd.concat(frames, ignore_index=True)
allp["site_key"] = modis.site_key(allp.lat, allp.lon, nd).values
multi = allp.groupby("site_key")[["lat", "lon"]].nunique()
multi = multi[(multi.lat > 1) | (multi.lon > 1)]
print("site keys with more than one distinct (lat, lon):", len(multi))
if len(multi):
    print(allp[allp.site_key.isin(multi.index)].sort_values("site_key").to_string())

for p in (old, new):
    p["h"], p["v"] = modis.sinusoidal_tiles(p.lon.values, p.lat.values, m)
t_old = set(map(tuple, old[["h", "v"]].values))
t_new = set(map(tuple, new[["h", "v"]].values))
print("tiles: Phase-1", len(t_old), "; current", len(t_new), "; tiles only in the current set:", sorted(t_new - t_old))
only = new[~new.site_key.isin(old.site_key)]
print("added points in tiles that had no Phase-1 point:",
      only[[tuple(x) not in t_old for x in only[["h", "v"]].values]][["site_key", "h", "v"]].values.tolist())

# synthetic NPP rasters, one per tile (500 m sinusoidal grid, 2400 x 2400), values with water/fill codes
px = m["tile_size_m"] / 2400
paths = {}
for h, v in sorted(t_new):
    f = SCR / f"npp_h{h:02d}v{v:02d}.tif"
    paths[(h, v)] = f
    if f.exists():
        continue
    x0 = m["x_origin_m"] + h * m["tile_size_m"]
    y0 = m["y_origin_m"] - v * m["tile_size_m"]
    r, c = np.mgrid[0:2400, 0:2400]
    a = ((r * 37 + c * 11 + h * 101 + v * 7) % 20000).astype("int16")
    a[(r % 97 == 0) | (c % 89 == 0)] = 32761          # out-of-range codes (masked as NaN)
    with rasterio.open(f, "w", driver="GTiff", width=2400, height=2400, count=1, dtype="int16",
                       crs=m["sinusoidal_proj"], transform=from_origin(x0, y0, px, px), compress="deflate",
                       predictor=2, tiled=True) as dst:
        dst.write(a, 1)


class Catalog:
    def search(self, collections, datetime, query, max_items):
        h, v = query["modis:horizontal-tile"]["eq"], query["modis:vertical-tile"]["eq"]
        its = [SimpleNamespace(id=f"MOD17A3HGF.A{y}.h{h:02d}v{v:02d}",
                               datetime=datetime_(y), properties={},
                               assets={"Npp_500m": SimpleNamespace(href=f"{paths[(h, v)]}|{y}")}) for y in range(2020, 2025)]
        return SimpleNamespace(item_collection=lambda: its)


def datetime_(y):
    return datetime(y, 1, 1, tzinfo=timezone.utc)


real_read = modis.read_windows
modis.read_windows = lambda href, sub, kind, mm: real_read(href.split("|")[0], sub, kind, mm)


class Tok:
    def get(self, force=False):
        return "tok"


res = {}
for name, p in (("old", old), ("new", new)):
    out, info = modis.extract_points(p[["lat", "lon", "site_key"]], m, kinds=("npp",), catalog=Catalog(), tokens=Tok())
    print(name, "n_jobs", info["n_jobs"], "failed", len(info["failed_reads"]), "gaps", info["catalog_gaps"][:3])
    res[name] = out.set_index("site_key")
c = res["old"].join(res["new"], lsuffix="_old", rsuffix="_new", how="inner")
same = (c.npp_old.values == c.npp_new.values) | (np.isnan(c.npp_old.values) & np.isnan(c.npp_new.values))
print("common points:", len(c), "; NPP bit-identical at all of them:", bool(same.all()),
      "; npp_n identical:", bool((c.npp_n_old == c.npp_n_new).all()))
locked_keys = set()
for tag in ("qc", "repo"):
    st = read_table(cfg, cfg.path("derived", f"sites_v3_{tag}.parquet"))
    locked_keys |= set(modis.site_key(st.lat, st.lon, nd))
print("locked-build keys covered by both runs:", len(locked_keys & set(c.index)), "of", len(locked_keys))
