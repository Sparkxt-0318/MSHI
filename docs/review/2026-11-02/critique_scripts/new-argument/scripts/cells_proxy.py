"""N2b/N2c 0.5-deg cell grids from the committed IGBP raster (exp_forest_bias.py L34-49, exp_poststrat.py L31-61 logic),
with PROXY climate at cell centres from legacy atlas_lookup.json (original-pipeline WorldClim)."""
import sys, json, numpy as np, pandas as pd, rasterio, rasterio.windows
LC, ATLAS, OUT = sys.argv[1:4]
cells = json.load(open(ATLAS))["cells"]
clim = pd.DataFrame([(c["lat"], c["lon"], c["fnpp"]["features"]["bio01"], c["fnpp"]["features"]["bio12"]) for c in cells],
                    columns=["lat", "lon", "bio01", "bio12"])
clim["key"] = (clim.lat * 4).round().astype(int).astype(str) + "_" + (clim.lon * 4).round().astype(int).astype(str)
frames = []
for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    with rasterio.open(LC) as s:
        arr = s.read(1, window=rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform))
    ny, nx = arr.shape
    LON, LAT = np.meshgrid(x0 + (np.arange(nx) + 0.5) * 0.05, y1 - (np.arange(ny) + 0.5) * 0.05)
    df = pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel()})
    df = df[df.c > 0]
    df["cx"], df["cy"] = np.floor(df.lon / 0.5), np.floor(df.lat / 0.5)
    df["cont"] = "Asia" if x0 == 25 else "North America"
    frames.append(df)
px = pd.concat(frames, ignore_index=True)
# per-cell counts by IGBP code
cnt = px.groupby(["cx", "cy", "cont", "c"]).size().unstack(fill_value=0)
cnt.columns = [f"n{int(c)}" for c in cnt.columns]
g = cnt.reset_index()
g["lon"], g["lat"] = g.cx * 0.5 + 0.25, g.cy * 0.5 + 0.25
g["key"] = (g.lat * 4).round().astype(int).astype(str) + "_" + (g.lon * 4).round().astype(int).astype(str)
g = g.merge(clim[["key", "bio01", "bio12"]], on="key", how="left")
for k in range(1, 18):
    if f"n{k}" not in g: g[f"n{k}"] = 0
g.to_parquet(OUT)
# coverage report for the N2b footprint
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
n_inc = g[inc].sum(1)
fp = g[n_inc >= 20]
w = np.cos(np.radians(fp.lat)) * n_inc[n_inc >= 20]
print("N2b footprint cells:", len(fp), " with atlas climate:", int(fp.bio01.notna().sum()),
      f" area share covered: {w[fp.bio01.notna()].sum() / w.sum():.3f}")
