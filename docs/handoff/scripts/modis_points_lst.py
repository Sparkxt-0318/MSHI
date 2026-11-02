"""Extract MODIS C6.1 NPP (MOD17A3HGF, 2020-2024 annual mean) and LST day/night (MOD11A2, first 8-day
composite of each month 2020-2024, mean) at site points as the mean of valid pixels in a 0.05 x 0.05 deg
window centred on the site. Source: Microsoft Planetary Computer COGs (anonymous SAS token).
Usage: python modis_points.py SITES.csv(site_key,lat,lon) OUT.parquet
"""
import sys, time, json, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
import pystac_client

pts = pd.read_csv(sys.argv[1]); OUT = sys.argv[2]
R, T = 6371007.181, 1111950.5197
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
tf = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
x, y = tf.transform(pts.lon.values, pts.lat.values)
pts["h"] = np.floor((x + 20015109.354) / T).astype(int); pts["v"] = np.floor((10007554.677 - y) / T).astype(int)
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
_tok = {}
import threading
_lock = threading.Lock()
def token(col, force=False):
    with _lock:
        if force or "t" not in _tok or time.time() - _tok["t"][1] > 240:
            for k in range(8):
                try:
                    j = requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/modiseuwest/modis-061-cogs", timeout=60).json()
                    _tok["t"] = (j["token"], time.time()); break
                except Exception:
                    time.sleep(5 * (k + 1))
        return _tok["t"][0]

def dt(it):
    return it.datetime or pd.Timestamp(it.properties["start_datetime"]).to_pydatetime()

def items_for(col, prefix, h, v):
    q = {"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}
    its = cat.search(collections=[col], datetime="2020-01-01/2024-12-31", query=q, max_items=500).item_collection()
    return [i for i in its if i.id.startswith(prefix)]

def read_windows(href, sub, kind):
    out = {}
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(href) as src:
            for _, p in sub.iterrows():
                xs, ys = tf.transform([p.lon - .025, p.lon + .025, p.lon - .025, p.lon + .025],
                                      [p.lat - .025, p.lat - .025, p.lat + .025, p.lat + .025])
                w = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
                a = src.read(1, window=w, boundless=True, fill_value=0).astype("float64")
                if kind == "npp":
                    a = np.where((a >= 0) & (a <= 32700), a * 0.1, np.nan)        # g C m-2 yr-1
                else:
                    a = np.where(a > 0, a * 0.02 - 273.15, np.nan)                # deg C
                out[p.site_key] = np.nanmean(a) if np.isfinite(a).any() else np.nan
    return out

jobs = []
for (h, v), sub in pts.groupby(["h", "v"]):
    for it in ([] if "--lst-only" in sys.argv else items_for("modis-17A3HGF-061", "MOD17A3HGF", h, v)):
        jobs.append(("npp", "modis-17A3HGF-061", it.assets["Npp_500m"].href, sub, dt(it).year))
    if "--npp-only" in sys.argv: continue
    lst = items_for("modis-11A2-061", "MOD11A2", h, v)
    firsts = {}
    for it in sorted(lst, key=lambda i: dt(i)):
        firsts.setdefault((dt(it).year, dt(it).month), it)
    for it in firsts.values():
        jobs.append(("lst_day", "modis-11A2-061", it.assets["LST_Day_1km"].href, sub, dt(it).year))
        jobs.append(("lst_night", "modis-11A2-061", it.assets["LST_Night_1km"].href, sub, dt(it).year))
print(f"{len(pts)} sites, {pts.groupby(['h','v']).ngroups} tiles, {len(jobs)} raster reads", flush=True)

acc = {}
def run(j):
    kind, col, href, sub, yr = j
    for attempt in range(4):
        try:
            return kind, read_windows(href + "?" + token(col), sub, "npp" if kind == "npp" else "lst")
        except Exception as e:
            time.sleep(3 * (attempt + 1)); err = e
            if "403" in str(e): token(col, force=True)
    print("FAILED", href, err, flush=True); return kind, {}
done = 0
with ThreadPoolExecutor(32) as ex:
    for f in as_completed([ex.submit(run, j) for j in jobs]):
        kind, vals = f.result()
        for k, val in vals.items(): acc.setdefault((k, kind), []).append(val)
        done += 1
        if done % 500 == 0: print(done, "/", len(jobs), flush=True)
rows = []
for k in pts.site_key:
    row = {"site_key": k}
    for kind in ["npp", "lst_day", "lst_night"]:
        v = np.array(acc.get((k, kind), []), float)
        row[kind] = np.nanmean(v) if np.isfinite(v).any() else np.nan
        row[kind + "_n"] = int(np.isfinite(v).sum())
    rows.append(row)
pd.DataFrame(rows).to_parquet(OUT, index=False)
print("wrote", OUT)
