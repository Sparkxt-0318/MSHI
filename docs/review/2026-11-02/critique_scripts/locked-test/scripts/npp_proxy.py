import sys
import numpy as np, pandas as pd, rasterio
W, M = sys.argv[1:3]
a = pd.read_parquet(f"{W}/out/asia_384.parquet")
with rasterio.open(f"{M}/npp_2020_2024_mean.tif") as s:
    print(s.profile["dtype"], s.nodata, s.res, s.bounds)
    v = np.array([x[0] for x in s.sample(list(zip(a.lon, a.lat)))], dtype=float)
    # 3x3 window: missing only if all 9 cells missing
    arr = s.read(1).astype(float); T = s.transform
    if s.nodata is not None: arr[arr == s.nodata] = np.nan
inv = ~T
w = []
for lo, la in zip(a.lon, a.lat):
    c, r = inv * (lo, la); r, c = int(np.floor(r)), int(np.floor(c))
    win = arr[max(r-1,0):r+2, max(c-1,0):c+2]; w.append(np.nanmean(win) if np.isfinite(win).any() else np.nan)
w = np.array(w)
print("single-pixel NaN:", int(np.isnan(v).sum()), "| zero:", int((v == 0).sum()), "| 3x3 all-NaN:", int(np.isnan(w).sum()))
b = (np.floor(a.lon / 5).astype(int).astype(str) + "_" + np.floor(a.lat / 5).astype(int).astype(str)).values
u, cnt = np.unique(b, return_counts=True); sing = set(u[cnt == 1])
miss = np.isnan(w)
print(a.loc[miss, ["site_id", "lat", "lon", "country", "ecosystem"]].assign(singleton=[bb in sing for bb in b[miss]]).to_string())
miss1 = np.isnan(v) | (v == 0)
print("single-pixel missing sites in singleton blocks:", int(sum(bb in sing for bb in b[miss1])), "of", int(miss1.sum()))
