"""0.5-deg footprint cells built with the handoff's own code (exp_forest_bias.py L34-49, verbatim except that all IGBP
codes are kept and counted so any crosswalk can be applied later). Climate: atlas cell centre (proxy for WorldClim 2.5'
sampled at the cell centre in the handoff, L51-52). Missing atlas cells: filled from nearest atlas cell within 1 deg."""
import sys, numpy as np, pandas as pd, rasterio, rasterio.windows
from sklearn.neighbors import BallTree
V = sys.argv[1]
LC = "/home/user/MSHI/data/raw/modis/landcover_igbp_2023.tif"
cells = []
for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    with rasterio.open(LC) as s:
        win = rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform)
        arr = s.read(1, window=win)
    ny, nx = arr.shape
    lat_c = y1 - (np.arange(ny) + 0.5) * 0.05; lon_c = x0 + (np.arange(nx) + 0.5) * 0.05
    LON, LAT = np.meshgrid(lon_c, lat_c)
    df = pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel()})
    df = df[df.c > 0]
    df["cell_x"] = np.floor(df.lon / 0.5); df["cell_y"] = np.floor(df.lat / 0.5)
    cnt = df.groupby(["cell_x", "cell_y", "c"]).size().unstack(fill_value=0)
    cnt.columns = [f"n{int(c)}" for c in cnt.columns]
    g = cnt.reset_index(); g["box"] = "Asia" if x0 == 25 else "NA"
    cells.append(g)
g = pd.concat(cells, ignore_index=True).fillna(0)
for k in range(1, 18):
    if f"n{k}" not in g: g[f"n{k}"] = 0
g["lon"] = g.cell_x * 0.5 + 0.25; g["lat"] = g.cell_y * 0.5 + 0.25
g["continent"] = np.where(g.box == "Asia", "Asia", "North America")
clim = pd.read_parquet(f"{V}/out/atlas_clim.parquet")
key = dict(zip(zip(clim.cx, clim.cy), zip(clim.bio01, clim.bio12)))
kk = list(zip(g.cell_x.astype(int), g.cell_y.astype(int)))
g["bio01"] = [key.get(k, (np.nan, np.nan))[0] for k in kk]; g["bio12"] = [key.get(k, (np.nan, np.nan))[1] for k in kk]
g["filled"] = g.bio01.isna()
t = BallTree(np.radians(clim[["lat", "lon"]].values), metric="haversine")
m = g.filled.values
dist, idx = t.query(np.radians(g.loc[m, ["lat", "lon"]].values), k=1)
ok = dist[:, 0] * 180 / np.pi <= 1.0
b1 = np.where(ok, clim.bio01.values[idx[:, 0]], np.nan); b12 = np.where(ok, clim.bio12.values[idx[:, 0]], np.nan)
g.loc[m, "bio01_fill"] = b1; g.loc[m, "bio12_fill"] = b12
g.to_parquet(f"{V}/out/cells_all_codes.parquet")
print(len(g), "cells;", int(m.sum()), "not in atlas;", int(ok.sum()), "fillable within 1 deg")
