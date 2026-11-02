"""Findings 05/06: emulate modis_points_lst.py tile choice + window (lines 14-18, 47-55) for every v3 site, using
rasterio's own from_bounds/round_offsets/round_lengths on the standard MODIS 500-m (NPP) tile transform, and run the
script's exact read + validity logic on a synthetic tile that contains in-tile fill (32767) and water (32766) pixels."""
import sys, numpy as np, pandas as pd, rasterio
from rasterio.transform import Affine
from rasterio.windows import from_bounds
from pyproj import Transformer
V = sys.argv[1]
R, T = 6371007.181, 1111950.5197
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
tf = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
NPIX = 2400; PS = T / NPIX
def tile_transform(h, v): return Affine(PS, 0, -20015109.354 + h * T, 0, -PS, 10007554.677 - v * T)
def window(lon, lat, h, v):
    xs, ys = tf.transform([lon - .025, lon + .025, lon - .025, lon + .025], [lat - .025, lat - .025, lat + .025, lat + .025])
    return from_bounds(min(xs), min(ys), max(xs), max(ys), tile_transform(h, v)).round_offsets().round_lengths()
out = []
for tag in ["qc", "repo"]:
    st = pd.read_parquet(f"{V}/out/v3/sites_v3_{tag}.parquet")
    x, y = tf.transform(st.lon.values, st.lat.values)
    st["h"] = np.floor((x + 20015109.354) / T).astype(int); st["v"] = np.floor((10007554.677 - y) / T).astype(int)
    rows = []
    for _, s in st.iterrows():
        w = window(s.lon, s.lat, s.h, s.v)
        r0, c0, hh, ww = int(w.row_off), int(w.col_off), int(w.height), int(w.width)
        rr = np.arange(r0, r0 + hh); cc = np.arange(c0, c0 + ww)
        inside = np.outer((rr >= 0) & (rr < NPIX), (cc >= 0) & (cc < NPIX))
        nominal_w = 0.05 * np.pi / 180 * R * np.cos(np.radians(s.lat)) / PS
        rows.append(dict(site_id=s.site_id, continent=s.continent, lat=s.lat, lon=s.lon, h=s.h, v=s.v, w=ww, hgt=hh, frac_out=1 - inside.mean(), xratio=ww / nominal_w))
    d = pd.DataFrame(rows); d["tag"] = tag; out.append(d)
    e = d[d.frac_out > 0]
    print(f"[{tag}] sites {len(d)}: window partly outside its tile: {len(e)} ({len(e)/len(d):.1%}); >=25% outside: {(d.frac_out >= .25).sum()}; exactly 50%: {np.isclose(d.frac_out, .5).sum()}; by continent:", e.continent.value_counts().to_dict())
    if tag == "qc":
        print(e.sort_values("frac_out", ascending=False)[["site_id", "continent", "lat", "lon", "h", "v", "w", "hgt", "frac_out"]].round(3).head(25).to_string(index=False))
        print("\nE-W window extent / nominal 0.05 deg, median (max) by continent:")
        print(d.groupby("continent").xratio.agg(["median", "max"]).round(2).to_string())
pd.concat(out).to_csv(f"{V}/out/modis_windows.csv", index=False)
# ---- synthetic tile test, exact read logic of lines 49-55
for (lat, lon) in [(40.0, 115.0), (40.0, 3.6), (45.3, 7.5)]:
    x, y = tf.transform([lon], [lat]); h = int(np.floor((x[0] + 20015109.354) / T)); v = int(np.floor((10007554.677 - y[0]) / T))
    arr = np.full((NPIX, NPIX), 5000, np.int16); arr[:, ::7] = 32767; arr[:, 3::11] = 32766    # some in-tile fill and water pixels
    prof = dict(driver="GTiff", width=NPIX, height=NPIX, count=1, dtype="int16", crs=SIN, transform=tile_transform(h, v), nodata=32767, tiled=True, blockxsize=512, blockysize=512)
    p = f"{V}/out/synth_h{h}v{v}.tif"
    with rasterio.open(p, "w", **prof) as dst: dst.write(arr, 1)
    with rasterio.open(p) as src:
        xs, ys = tf.transform([lon - .025, lon + .025, lon - .025, lon + .025], [lat - .025, lat - .025, lat + .025, lat + .025])
        w = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
        a = src.read(1, window=w, boundless=True, fill_value=0).astype("float64")
        n0 = int((a == 0).sum()); nfill = int((a == 32767).sum())
        a = np.where((a >= 0) & (a <= 32700), a * 0.1, np.nan)
        print(f"synthetic ({lat},{lon}) tile h{h}v{v}: window {w}; pixels {a.size}, zeros {n0}, in-tile 32767 kept as 32767: {nfill}; window mean NPP = {np.nanmean(a):.1f} (true 500)")
