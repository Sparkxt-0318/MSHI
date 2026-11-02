"""Synthetic 2400x2400 int16 tile in MODIS sinusoidal (h=26, v=4), every pixel = 5000 (NPP 500 g C), nodata=32767
(as MOD17A3HGF). Read exactly as modis_points_lst.read_windows does for a site at 40.0N 115.0E (window straddles v=4/5)."""
import numpy as np, rasterio, sys
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from pyproj import Transformer
out = sys.argv[1]
T = 1111950.5197; px = T / 2400; h, v = 26, 4
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
tr = from_origin(-20015109.354 + h * T, 10007554.677 - v * T, px, px)
with rasterio.open(out, "w", driver="GTiff", width=2400, height=2400, count=1, dtype="int16", crs=SIN, transform=tr, nodata=32767) as d:
    d.write(np.full((2400, 2400), 5000, "int16"), 1)
tf = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
lon, lat = 115.0, 40.0
with rasterio.open(out) as src:
    xs, ys = tf.transform([lon - .025, lon + .025, lon - .025, lon + .025], [lat - .025, lat - .025, lat + .025, lat + .025])
    w = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
    a = src.read(1, window=w, boundless=True, fill_value=0).astype("float64")
    print("window", w, "pixels", a.size, "zeros", int((a == 0).sum()))
    a = np.where((a >= 0) & (a <= 32700), a * 0.1, np.nan)
    print("window-mean NPP (g C m-2 yr-1):", np.nanmean(a), " true value: 500.0")
