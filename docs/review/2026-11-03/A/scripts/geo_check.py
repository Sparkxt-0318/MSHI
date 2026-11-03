"""mshi.geo.geodesic_km vs a brute-force reference (pyproj.Geod on densified polygon edges) on random points and
polygons (poles, antimeridian, real Natural Earth countries); nearest_within_km vs brute force."""
import math
import sys
import time

import numpy as np
from pyproj import Geod
from shapely.geometry import MultiPolygon, Point, Polygon, box

sys.path.insert(0, "/home/user/MSHI")
from mshi.geo import geodesic_km, nearest_within_km  # noqa: E402

G = Geod(ellps="WGS84")


def rings(geom):
    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    for p in polys:
        yield np.asarray(p.exterior.coords)
        for r in p.interiors:
            yield np.asarray(r.coords)


def ref_km(lon, lat, geom, step=0.002):
    """Min geodesic distance from the point to the polygon boundary, edges densified in lon/lat (the polygon's
    edges are straight in lon/lat, as GIS treats EPSG:4326 data); 0 inside."""
    if geom.contains(Point(lon, lat)):
        return 0.0
    best = math.inf
    for c in rings(geom):
        seg = np.diff(c, axis=0)
        n = np.maximum(1, np.ceil(np.abs(seg).max(1) / step).astype(int))
        pts = [c[:-1][i] + seg[i] * (np.arange(n[i])[:, None] / n[i]) for i in range(len(seg))]
        pts = np.vstack(pts + [c[-1:]])
        _, _, d = G.inv(np.full(len(pts), lon), np.full(len(pts), lat), pts[:, 0], pts[:, 1])
        best = min(best, float(d.min()) / 1000.0)
    return best


rng = np.random.default_rng(12345)
worst = []
t0 = time.time()
# 1) random boxes near random points, including poles and the antimeridian
cases = []
for k in range(400):
    kind = k % 4
    if kind == 0:
        lat, lon = rng.uniform(-80, 80), rng.uniform(-180, 180)
    elif kind == 1:                     # near the poles
        lat, lon = rng.choice([-1, 1]) * rng.uniform(80, 89.5), rng.uniform(-180, 180)
    elif kind == 2:                     # near the antimeridian
        lat, lon = rng.uniform(-70, 70), rng.choice([-1, 1]) * rng.uniform(178.5, 180)
    else:
        lat, lon = rng.uniform(-60, 60), rng.uniform(-180, 180)
    # box at an offset of 0.1-1.5 deg, size 0.05-1 deg (wrapped into [-180, 180])
    dlat, dlon = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5) / max(0.05, math.cos(math.radians(lat)))
    w, h = rng.uniform(0.05, 1.0), rng.uniform(0.05, 1.0)
    cy = float(np.clip(lat + dlat, -89.9 + h / 2, 89.9 - h / 2))
    cx = lon + dlon
    cx = (cx + 180) % 360 - 180
    x0, x1 = cx - w / 2, cx + w / 2
    if x0 < -180:
        g = MultiPolygon([box(-180, cy - h / 2, x1, cy + h / 2), box(x0 + 360, cy - h / 2, 180, cy + h / 2)])
    elif x1 > 180:
        g = MultiPolygon([box(x0, cy - h / 2, 180, cy + h / 2), box(-180, cy - h / 2, x1 - 360, cy + h / 2)])
    else:
        g = box(x0, cy - h / 2, x1, cy + h / 2)
    cases.append((lon, lat, g, kind))
errs = []
for lon, lat, g, kind in cases:
    a = geodesic_km(lon, lat, g, max_km=2000.0)
    b = ref_km(lon, lat, g)
    if b > 2000:
        continue
    errs.append((abs(a - b), a, b, lon, lat, kind, g.bounds))
errs.sort(key=lambda e: -e[0])
print(f"random boxes: {len(errs)} cases; max |diff| {errs[0][0]:.3f} km; 99th pct "
      f"{np.quantile([e[0] for e in errs], 0.99):.3f} km; median {np.median([e[0] for e in errs]):.4f} km")
for e in errs[:6]:
    print("   |diff| %.3f km  geo %.3f  ref %.3f  pt (%.3f, %.3f) kind %d  box %s" % (e[0], e[1], e[2], e[3], e[4], e[5],
                                                                                 tuple(round(x, 3) for x in e[6])))
by = {}
for e in errs:
    by.setdefault(e[5], []).append(e[0] / max(e[2], 1e-9))
print("   max relative error by kind (0 random, 1 poles, 2 antimeridian, 3 random):",
      {k: round(max(v), 5) for k, v in by.items()})
# distances > max_km must be inf; < max_km must be finite
inf_bad = 0
for lon, lat, g, kind in cases[:100]:
    a = geodesic_km(lon, lat, g, max_km=50.0)
    b = ref_km(lon, lat, g)
    if (a == math.inf) != (b > 50.0) and abs(b - 50.0) > 0.5:
        inf_bad += 1
        print("   max_km cut-off disagrees:", lon, lat, a, b)
print("max_km=50 cut-off disagreements (beyond 0.5 km of the limit):", inf_bad)
print("seconds", round(time.time() - t0, 1))

# 2) real Natural Earth countries near coasts / borders
import geopandas as gpd  # noqa: E402
from mshi.config import load_config  # noqa: E402
from mshi.data.sites_analysis import countries  # noqa: E402
cfg = load_config()
cty = countries(cfg)
names = ["Italy", "Malta", "Pakistan", "India", "China", "Vietnam", "Norway", "Russia", "Fiji", "New Zealand",
         "Canada", "Chile", "Indonesia", "United States of America", "Greenland", "Japan"]
errs2 = []
t0 = time.time()
for nm in names:
    g = cty.set_index("ADMIN").geometry.loc[nm]
    minx, miny, maxx, maxy = g.bounds
    for _ in range(12):
        # a random boundary vertex, offset by up to ~1.2 deg
        polys = [g] if isinstance(g, Polygon) else list(g.geoms)
        p = polys[rng.integers(len(polys))]
        c = np.asarray(p.exterior.coords)
        v = c[rng.integers(len(c))]
        lat = float(np.clip(v[1] + rng.uniform(-1.0, 1.0), -89.5, 89.5))
        lon = float((v[0] + rng.uniform(-1.2, 1.2) + 180) % 360 - 180)
        a = geodesic_km(lon, lat, g, max_km=2000.0)
        b = ref_km(lon, lat, g, step=0.005)
        errs2.append((abs(a - b), a, b, nm, lon, lat))
errs2.sort(key=lambda e: -e[0])
print(f"Natural Earth countries: {len(errs2)} points; max |diff| {errs2[0][0]:.3f} km; median "
      f"{np.median([e[0] for e in errs2]):.4f} km; seconds {time.time() - t0:.0f}")
for e in errs2[:5]:
    print("   |diff| %.3f km  geo %.3f  ref %.3f  %s (%.3f, %.3f)" % e)

# 3) the ten records whose flag changed and every flagged record within 90-110 km
import pandas as pd  # noqa: E402
A = pd.read_parquet("/home/user/MSHI/data/derived/records_analysis.parquet")
near = A[(A.dist_to_reported_country_km > 85) & (A.dist_to_reported_country_km < 115)]
gi = cty.set_index("ADMIN").geometry
rows = []
for r in near.itertuples():
    b = ref_km(r.lon, r.lat, gi.loc[r.reported_country_norm], step=0.002)
    rows.append((r.rec_id, r.Country, r.geo_country, r.dist_to_reported_country_km, b, bool(r.f_coord), b > 100.0))
print("records 85-115 km from their reported country: rec_id, Country, geo_country, geodesic_km (pipeline), "
      "reference km, f_coord, reference > 100")
for x in rows:
    print("  ", x, "" if x[5] == x[6] else "  <-- FLAG WOULD DIFFER")

# 4) nearest_within_km vs brute force over the subunits
from mshi.geo import subunits  # noqa: E402
su = subunits(cfg)
pts = [(-9.65, 38.7), (14.0, 36.2), (-16.0, 28.6), (179.95, -16.5), (-179.95, -16.6), (-171.0, 65.6), (179.5, 71.2),
       (-61.0, 14.9), (-52.5, 5.6), (100.0, 1.0), (-155.0, 19.0), (19.0, 54.6), (-70.5, -54.9), (166.4, -78.0)]
for lon, lat in pts:
    k, km = nearest_within_km(lon, lat, su.geometry, 50.0)
    win = su[su.intersects(box(lon - 3, lat - 3, lon + 3, lat + 3)) |
             su.intersects(box((lon + 180) % 360 - 183, lat - 3, (lon + 180) % 360 - 177, lat + 3))]
    ref = sorted((ref_km(lon, lat, g, step=0.01), su.loc[i, "SUBUNIT"]) for i, g in win.geometry.items())
    rk = ref[0] if ref else (math.inf, None)
    print(f"  nearest ({lon}, {lat}): mshi {su.loc[k, 'SUBUNIT'] if k is not None else None} {km:.2f} km; "
          f"brute force {rk[1]} {rk[0]:.2f} km{'' if (k is None) == (rk[0] > 50) else ''}")
