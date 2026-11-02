"""Synthetic MODIS-like sinusoidal GeoTIFFs + point set (real QC-site coordinates in 5 tiles, plus tile-edge
points, an all-fill NPP point and an empty tile)."""
import hashlib, os, sys
import numpy as np, pandas as pd, rasterio
from rasterio.transform import from_origin
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mshi.config import load_config
from mshi.data.modis import sinusoidal_tiles, site_key
from fakepc import TILES, catalog_items

m = load_config()["sources"]["modis"]
R, T, X0, Y0 = 6371007.181, m["tile_size_m"], m["x_origin_m"], m["y_origin_m"]
s = pd.read_parquet("/home/user/MSHI/data/derived/sites_v3_qc.parquet")[["lat", "lon"]]
s["h"], s["v"] = sinusoidal_tiles(s.lon.values, s.lat.values, m)
s["x"] = R * np.radians(s.lon) * np.cos(np.radians(s.lat))
s["y"] = R * np.radians(s.lat)
top = s.groupby(["h", "v"]).size().sort_values(ascending=False)
tiles = [t for t in top.index[:6]]
pts = []
for (h, v) in tiles[:5]:
    sub = s[(s.h == h) & (s.v == v)]
    d = np.hypot(sub.x.values[:, None] - sub.x.values[None], sub.y.values[:, None] - sub.y.values[None])
    c = np.argmax((d < 60e3).sum(1))
    near = sub[d[c] < 60e3].head(10)
    pts.append(near[["lat", "lon", "h", "v"]].assign(kind="site"))
empty = tiles[5]
pts.append(s[(s.h == empty[0]) & (s.v == empty[1])].head(2)[["lat", "lon", "h", "v"]].assign(kind="empty_tile"))
# tile-edge points in the first tile: 0.3-2 km inside its left and top edges and its top-left corner
h0, v0 = tiles[0]
left, topy = X0 + h0 * T, Y0 - v0 * T
edge = []
for dx, dy in [(300, 40e3), (1000, 45e3), (2000, 50e3), (40e3, 300), (45e3, 1000), (50e3, 2000), (500, 500), (1500, 800)]:
    x, y = left + dx, topy - dy
    lat = np.degrees(y / R)
    lon = np.degrees(x / (R * np.cos(np.radians(lat))))
    edge.append((lat, lon, h0, v0, "edge"))
pts.append(pd.DataFrame(edge, columns=["lat", "lon", "h", "v", "kind"]))
P = pd.concat(pts, ignore_index=True)
hh, vv = sinusoidal_tiles(P.lon.values, P.lat.values, m)
assert (hh == P.h.values).all() and (vv == P.v.values).all()
P["site_key"] = site_key(P.lat, P.lon).values
assert P.site_key.is_unique
P[["site_key", "lat", "lon"]].to_csv("sites.csv", index=False)
P.to_csv("sites_meta.csv", index=False)
fillpt = P[P.kind == "site"].iloc[0]          # NPP all-fill around this point (every year)

os.makedirs(TILES, exist_ok=True)


def grid(h, v, px, sub, margin=15e3):
    tl, tt = X0 + h * T, Y0 - v * T
    xs = R * np.radians(sub.lon.values) * np.cos(np.radians(sub.lat.values))
    ys = R * np.radians(sub.lat.values)
    x0, x1 = max(tl, xs.min() - margin), min(tl + T, xs.max() + margin)
    y1, y0 = min(tt, ys.max() + margin), max(tt - T, ys.min() - margin)
    c0, c1 = int(np.floor((x0 - tl) / px)), int(np.ceil((x1 - tl) / px))
    r0, r1 = int(np.floor((tt - y1) / px)), int(np.ceil((tt - y0) / px))
    return from_origin(tl + c0 * px, tt - r0 * px, px, px), c1 - c0, r1 - r0


def write(path, arr, tr, dtype):
    with rasterio.open(path + "?tok", "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype=dtype, transform=tr, crs=m["sinusoidal_proj"], compress="deflate") as dst:
        dst.write(arr.astype(dtype), 1)


n_files = 0
for (h, v) in tiles[:5]:
    sub = P[(P.h == h) & (P.v == v)]
    npp_items, lst_items = catalog_items(h, v, ties=True)
    for it in npp_items + lst_items:
        if not it.id.startswith(("MOD17A3HGF", "MOD11A2")):
            continue                     # Aqua items: no file (reading one would fail loudly)
        for a, asset in it.assets.items():
            rng = np.random.default_rng(int(hashlib.sha256(asset.href.encode()).hexdigest()[:12], 16))
            if a == "Npp_500m":
                tr, W, H = grid(h, v, T / 2400, sub)
                coarse = rng.integers(200, 12000, size=(H // 9 + 2, W // 9 + 2))
                arr = np.kron(coarse, np.ones((9, 9), int))[:H, :W] + rng.integers(-180, 180, (H, W))
                u = rng.random((H, W))
                arr[u < .05] = 32767; arr[(u >= .05) & (u < .08)] = rng.integers(32761, 32767)
                arr[(u >= .08) & (u < .10)] = 0; arr[(u >= .10) & (u < .105)] = -3000
                if (h, v) == (fillpt.h, fillpt.v):
                    x = R * np.radians(fillpt.lon) * np.cos(np.radians(fillpt.lat)); y = R * np.radians(fillpt.lat)
                    c = int((x - tr.c) / tr.a); r = int((y - tr.f) / tr.e)
                    arr[max(r - 25, 0):r + 25, max(c - 25, 0):c + 25] = 32767
                write(asset.href, arr, tr, "int16")
            else:
                tr, W, H = grid(h, v, T / 1200, sub)
                coarse = rng.integers(12800, 16200, size=(H // 5 + 2, W // 5 + 2))
                arr = np.kron(coarse, np.ones((5, 5), int))[:H, :W] + rng.integers(-60, 60, (H, W))
                arr[rng.random((H, W)) < .18] = 0
                if rng.random() < .15:       # a cloudy composite: whole raster missing
                    arr[:] = 0
                write(asset.href, arr, tr, "uint16")
            n_files += 1
print("tiles with items:", tiles[:5], "empty tile:", empty, "points:", len(P), P.kind.value_counts().to_dict(),
      "files:", n_files, "fill point:", fillpt.site_key)
open("tiles.txt", "w").write(repr([tuple(map(int, t)) for t in tiles[:5]]))
