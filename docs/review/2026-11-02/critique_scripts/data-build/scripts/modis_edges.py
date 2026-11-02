"""Emulate modis_points_lst.py window geometry (no network): for each v3 site, the tile (h,v) chosen from the point,
the 0.05 deg window transformed to sinusoidal, rasterio from_bounds + round_offsets/round_lengths, and the share of the
window lying outside the tile (filled with 0 by boundless=True, fill_value=0)."""
import sys, math, numpy as np, pandas as pd, rasterio
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from pyproj import Transformer
V3, NPPGEE = sys.argv[1], sys.argv[2]
T = 1111950.5197; X0, Y0 = -20015109.354, 10007554.677
tf = Transformer.from_crs("EPSG:4326", "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext", always_xy=True)
pts = pd.concat([pd.read_parquet(f"{V3}/sites_v3_qc.parquet").assign(tab="qc"), pd.read_parquet(f"{V3}/sites_v3_repo.parquet").assign(tab="repo")])
pts["site_key"] = pts.lat.round(5).astype(str) + "_" + pts.lon.round(5).astype(str)
x, y = tf.transform(pts.lon.values, pts.lat.values)
pts["h"] = np.floor((x + 20015109.354) / T).astype(int); pts["v"] = np.floor((10007554.677 - y) / T).astype(int)
def out_frac(row, npix):
    px = T / npix
    tr = from_origin(X0 + row.h * T, Y0 - row.v * T, px, px)
    xs, ys = tf.transform([row.lon - .025, row.lon + .025, row.lon - .025, row.lon + .025], [row.lat - .025, row.lat - .025, row.lat + .025, row.lat + .025])
    w = from_bounds(min(xs), min(ys), max(xs), max(ys), tr).round_offsets().round_lengths()
    c0, r0, W, H = int(w.col_off), int(w.row_off), int(w.width), int(w.height)
    cin = max(0, min(c0 + W, npix) - max(c0, 0)); rin = max(0, min(r0 + H, npix) - max(r0, 0))
    return 1 - (cin * rin) / (W * H) if W * H else np.nan, W * H
res = pts.apply(lambda r: out_frac(r, 2400), axis=1, result_type="expand"); pts["out_npp"], pts["npix_npp"] = res[0], res[1]
res = pts.apply(lambda r: out_frac(r, 1200), axis=1, result_type="expand"); pts["out_lst"], pts["npix_lst"] = res[0], res[1]
for tab in ["qc", "repo"]:
    p = pts[pts.tab == tab]
    a = p[p.out_npp > 0]
    print(f"{tab}: {len(p)} sites; NPP window partly outside its tile: {len(a)} sites; outside share median {a.out_npp.median():.2f}, max {a.out_npp.max():.2f}; >=25%: {(a.out_npp>=.25).sum()}")
    print("   by continent:", a.continent.value_counts().to_dict())
    print("   LST windows partly outside tile:", int((p.out_lst > 0).sum()))
u = pts.drop_duplicates("site_key")
print("unique site_keys across qc+repo:", len(u), "(README says LST run had 1,530 points)")
a = pts[(pts.tab == "qc") & (pts.out_npp > 0)].copy()
# expected NPP under-estimate if in-tile pixels are valid: factor (1 - out share); compare GEE 0.05deg NPP at those sites
with rasterio.open(NPPGEE) as s:
    a["npp_gee"] = [v[0] for v in s.sample(list(zip(a.lon, a.lat)))]
pd.set_option("display.width", 250)
print(a.sort_values("out_npp", ascending=False)[["site_id", "lat", "lon", "continent", "h", "v", "out_npp", "npix_npp", "npp_gee"]].head(25).round(3).to_string())
# why: SRDB coordinates on round degrees -> windows straddle tile rows at multiples of 10 deg latitude, or lon=0
print("QC sites with |lat - nearest multiple of 10| <= 0.025:", int((np.abs(pts[pts.tab=='qc'].lat - 10*np.round(pts[pts.tab=='qc'].lat/10)) <= 0.025).sum()))
