"""exp_forest_bias.py sample + shares (no WorldClim: the bio01/bio12 dropna and cell-centre WorldClim filter are not applied)."""
import sys, numpy as np, pandas as pd, rasterio, rasterio.windows
SITES, LC = sys.argv[1:3]
def samp(path, lon, lat):
    with rasterio.open(path) as s:
        return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)
d = pd.read_parquet(SITES)
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest", "Mixed forests": "Forest"}
d["plot_forest"] = d.ecosystem.replace(rep).eq("Forest").astype(int)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d = d[inbox & d.continent.isin(["Asia", "North America"])].dropna(subset=["log_rs"]).copy()
code = samp(LC, d.lon.values, d.lat.values)
print("in-box Asia/NA sites:", len(d), " code==0 (outside raster footprint):", int((code == 0).sum()))
d = d[code > 0].copy(); d["code"] = code[code > 0].astype(int)
print("N2b-like n (before WorldClim dropna):", len(d), " [handoff n=578]")
print("plot forest share:", round(d.plot_forest.mean(), 3), " [handoff 0.685]")
for nm, cl in [("IGBP 1-5 (handoff)", [1, 2, 3, 4, 5]), ("IGBP 1-5 + 8 woody savanna", [1, 2, 3, 4, 5, 8]), ("IGBP 1-5 + 8 + 9", [1, 2, 3, 4, 5, 8, 9])]:
    pf = d.code.isin(cl)
    print(f"  pixel forest share {nm:28s}: {pf.mean():.3f};  forest plots in such pixels: {pf[d.plot_forest == 1].mean():.3f};"
          f"  non-forest plots in such pixels: {pf[d.plot_forest == 0].mean():.3f}")
print("by continent: plot forest", d.groupby("continent").plot_forest.mean().round(3).to_dict(),
      " pixel(1-5)", d.groupby("continent").code.apply(lambda c: c.isin([1,2,3,4,5]).mean()).round(3).to_dict(),
      " pixel(1-5,8)", d.groupby("continent").code.apply(lambda c: c.isin([1,2,3,4,5,8]).mean()).round(3).to_dict())
d.to_parquet(sys.argv[3])
# landscape share over N2b footprint (exp_forest_bias.py L34-54 logic, but no WorldClim cell filter)
for forest_codes, nm in [([1, 2, 3, 4, 5], "1-5"), ([1, 2, 3, 4, 5, 8], "1-5+8")]:
    tot = []
    for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
        with rasterio.open(LC) as s:
            win = rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform); arr = s.read(1, window=win)
        ny, nx = arr.shape
        lat_c = y1 - (np.arange(ny) + 0.5) * 0.05; lon_c = x0 + (np.arange(nx) + 0.5) * 0.05
        LON, LAT = np.meshgrid(lon_c, lat_c)
        df = pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel()})
        df = df[(df.c > 0) & ~df.c.isin([13, 15, 16, 17])]
        df["cell_x"] = np.floor(df.lon / 0.5); df["cell_y"] = np.floor(df.lat / 0.5); df["f"] = df.c.isin(forest_codes)
        g = df.groupby(["cell_x", "cell_y"]).agg(f=("f", "mean"), n=("f", "size")).reset_index()
        g = g[g.n >= 20]; g["lat"] = g.cell_y * 0.5 + 0.25
        g["w"] = np.cos(np.radians(g.lat)) * g.n
        tot.append(g)
    g = pd.concat(tot)
    print(f"landscape forest share (area-weighted, N2b footprint, {nm}): {np.average(g.f, weights=g.w):.3f}  cells={len(g)}  [handoff 1-5: 0.198, cells 27655]")
    print("   window shape check:", arr.shape)
