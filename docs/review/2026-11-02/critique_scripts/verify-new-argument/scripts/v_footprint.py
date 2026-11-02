"""Finding 07: continent composition of the N2b/N2c/N2d landscape footprints, by rasterising Natural Earth 1:50m
countries (Russia split at 60E, as in build_sites_v3.py L52-54) onto the same 0.05-deg pixels the handoff reads."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio, rasterio.windows, rasterio.features
from shapely.geometry import box
LC = "/home/user/MSHI/data/raw/modis/landcover_igbp_2023.tif"
cty = gpd.read_file("/home/user/MSHI/data/raw/naturalearth/v5.1.2/ne_50m_admin_0_countries.geojson")[["ADMIN", "CONTINENT", "geometry"]]
rus = cty[cty.ADMIN == "Russia"]
eu = gpd.clip(rus, box(-180, -90, 60, 90)).assign(CONTINENT="Europe"); asia = gpd.clip(rus, box(60, -90, 180, 90)).assign(CONTINENT="Asia")
cty = pd.concat([cty[cty.ADMIN != "Russia"], eu, asia], ignore_index=True)
conts = sorted(cty.CONTINENT.unique()); cid = {c: i + 1 for i, c in enumerate(conts)}
rows = []
for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    with rasterio.open(LC) as s:
        win = rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform); arr = s.read(1, window=win)
    ny, nx = arr.shape
    tr = rasterio.transform.from_origin(x0, y1, 0.05, 0.05)   # the grid the handoff ASSUMES (L41)
    lab = rasterio.features.rasterize(((geom, cid[c]) for geom, c in zip(cty.geometry, cty.CONTINENT)), out_shape=(ny, nx), transform=tr, fill=0, dtype="uint8")
    lat_c = y1 - (np.arange(ny) + 0.5) * 0.05; lon_c = x0 + (np.arange(nx) + 0.5) * 0.05
    LON, LAT = np.meshgrid(lon_c, lat_c)
    rows.append(pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel(), "cont": lab.ravel(), "box": "Asia" if x0 == 25 else "NA"}))
px = pd.concat(rows, ignore_index=True); px = px[px.c > 0]
px["cx"] = np.floor(px.lon / 0.5); px["cy"] = np.floor(px.lat / 0.5)
inv = {v: k for k, v in cid.items()}; inv[0] = "off-polygon"
for name, excl in [("N2b {13,15,16,17}", [13, 15, 16, 17]), ("N2c {11,13,15,17}", [11, 13, 15, 17]), ("N2d {11,13,15,16,17}", [11, 13, 15, 16, 17])]:
    q = px[~px.c.isin(excl)].copy()
    n = q.groupby(["box", "cx", "cy"]).size().rename("n"); q = q.join(n, on=["box", "cx", "cy"]); q = q[q.n >= 20]
    q["w"] = np.cos(np.radians(q.cy * 0.5 + 0.25))   # handoff weights pixels by the cell-centre latitude
    sh = q.groupby(q.cont.map(inv)).w.sum() / q.w.sum()
    print(name, {k: round(float(v), 3) for k, v in sh.sort_values(ascending=False).items()})
    if name.startswith("N2c"):
        dsh = q[q.c == 16].groupby(q[q.c == 16].cont.map(inv)).w.sum() / q[q.c == 16].w.sum()
        print("   barren (16) area by continent:", {k: round(float(v), 3) for k, v in dsh.sort_values(ascending=False).items()})
        a = q[q.box == "Asia"]; sh2 = a.groupby(a.cont.map(inv)).w.sum() / a.w.sum()
        print("   Asia box only:", {k: round(float(v), 3) for k, v in sh2.sort_values(ascending=False).items()})
        b = q[q.box == "NA"]; 
        # country split within the NA box
