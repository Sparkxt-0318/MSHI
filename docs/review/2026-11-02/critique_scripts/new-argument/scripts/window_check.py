import sys, numpy as np, rasterio, rasterio.windows, pandas as pd
LC, NPP, S = sys.argv[1:4]
with rasterio.open(LC) as s:
    w = rasterio.windows.from_bounds(25, -10, 180, 80, s.transform); a = s.read(1, window=w); full = s.read(1); T = s.transform
print("window:", w, "shape", a.shape)
r0 = (T.f - 80) / 0.05
for off in (int(np.floor(r0)), int(np.ceil(r0))):
    sub = full[off:off + a.shape[0], 4100:4100 + a.shape[1]]
    print(f"  equals source rows starting at {off}: {np.array_equal(sub, a)}; true centre lat of window row 0 = {T.f - (off + .5) * .05:.5f} vs assumed {80 - .025:.5f}")
# share of window pixels that the handoff assigns to a different 0.5-deg cell than their true centre implies
ny = a.shape[0]; lat_assumed = 80 - (np.arange(ny) + .5) * .05
for off in (int(np.floor(r0)),):
    lat_true = T.f - (off + np.arange(ny) + .5) * .05
    print("  rows assigned to a different 0.5-deg cell row:", np.mean(np.floor(lat_assumed / .5) != np.floor(lat_true / .5)).round(3))
# N1: in-box Asia/NA sites with NPP finite & > 0 at their pixel (exp_selection_bias.py L51/L55)
d = pd.read_parquet(S)
with rasterio.open(NPP) as s: v = np.array([x[0] for x in s.sample(list(zip(d.lon, d.lat)))], float)
ok = np.isfinite(v) & (v > 0)
print(f"N1: in-box Asia/NA sites {len(d)}, NPP valid {ok.sum()} ({ok.mean():.3f}); dropped by IGBP code:", pd.Series(d.code[~ok]).value_counts().to_dict())
print("   plot-forest share kept vs dropped:", round(d.plot_forest[ok].mean(), 3), round(d.plot_forest[~ok].mean(), 3))
