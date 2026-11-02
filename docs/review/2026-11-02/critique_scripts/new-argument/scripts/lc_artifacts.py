import numpy as np, rasterio, sys
from scipy import ndimage
with rasterio.open(sys.argv[1]) as s:
    a = s.read(1); T = s.transform
ny, nx = a.shape
lat = T.f + (np.arange(ny) + 0.5) * T.e
lon = T.c + (np.arange(nx) + 0.5) * T.a
LAT = np.repeat(lat[:, None], nx, 1)
# 1) snow/ice (15) by latitude band
m15 = a == 15
print("class 15 (snow/ice) pixels total:", int(m15.sum()))
for lo, hi in [(-40, -23.5), (-23.5, 23.5), (23.5, 40), (40, 60), (60, 90)]:
    mm = m15 & (LAT >= lo) & (LAT < hi)
    print(f"  lat [{lo},{hi}): {int(mm.sum())}")
# tropical 15 pixels: are they adjacent to water (17)?
water = a == 17
nbw = ndimage.binary_dilation(water, structure=np.ones((3, 3)))
trop = (np.abs(LAT) < 23.5)
print("  tropical 15 adjacent to water:", int((m15 & trop & nbw).sum()), "of", int((m15 & trop).sum()))
# 2) code frequency in land pixels adjacent to water vs interior, tropics 10S-10N, 95-150E (SE Asia)
reg = (LAT > -10) & (LAT < 10) & (np.repeat(lon[None, :], ny, 0) > 95) & (np.repeat(lon[None, :], ny, 0) < 150)
land = (a > 0) & (a != 17)
coast = land & nbw & reg; inner = land & ~ndimage.binary_dilation(water, structure=np.ones((7, 7))) & reg
for nm, mk in [("coastal land (adj. to 17)", coast), ("interior land (>=3 px from 17)", inner)]:
    u, c = np.unique(a[mk], return_counts=True)
    print(nm, "n=", int(mk.sum()), {int(k): round(v / mk.sum(), 3) for k, v in zip(u, c)})
