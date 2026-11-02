"""Point set for the MODIS re-check: real QC-site coordinates (only lat/lon of the committed site table, from
the scratch git-archive copy) in the 3 tiles with most sites, 8 tile-edge points 0.3-2 km inside the first
tile's left/top edges, 2 points in a 4th tile (used as an 'empty' tile in gap tests).
usage: gen_points.py OUTDIR"""
import os, sys
SCR = "fixcheck3_scripts/modis-rasters"
sys.path.insert(0, f"{SCR}/pkg/head")
import numpy as np, pandas as pd
from mshi.config import load_config
from mshi.data.modis import sinusoidal_tiles, site_key

OUT = sys.argv[1]
m = load_config()["sources"]["modis"]
R, T, X0, Y0 = 6371007.181, m["tile_size_m"], m["x_origin_m"], m["y_origin_m"]
s = pd.read_parquet(f"{SCR}/pkg/head/data/derived/sites_v3_qc.parquet")[["lat", "lon"]]
s["h"], s["v"] = sinusoidal_tiles(s.lon.values, s.lat.values, m)
s["x"] = R * np.radians(s.lon) * np.cos(np.radians(s.lat))
s["y"] = R * np.radians(s.lat)
top = s.groupby(["h", "v"]).size().sort_values(ascending=False)
tiles = list(top.index[:4])
pts = []
for (h, v) in tiles[:3]:
    sub = s[(s.h == h) & (s.v == v)]
    d = np.hypot(sub.x.values[:, None] - sub.x.values[None], sub.y.values[:, None] - sub.y.values[None])
    c = np.argmax((d < 60e3).sum(1))
    pts.append(sub[d[c] < 60e3].head(8)[["lat", "lon", "h", "v"]].assign(kind="site"))
e = tiles[3]
pts.append(s[(s.h == e[0]) & (s.v == e[1])].head(2)[["lat", "lon", "h", "v"]].assign(kind="tile4"))
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
os.makedirs(OUT, exist_ok=True)
P[["site_key", "lat", "lon"]].to_csv(f"{OUT}/sites.csv", index=False)
P[P.kind != "tile4"][["site_key", "lat", "lon"]].to_csv(f"{OUT}/sites3.csv", index=False)
P.to_csv(f"{OUT}/sites_meta.csv", index=False)
print("tiles:", [tuple(map(int, t)) for t in tiles], "points:", P.kind.value_counts().to_dict())
