"""Area D end-to-end, step 1: a full sandbox with absolute scratch paths and stand-ins for the blocked sources.

- configs: <E2E>/v3_sandbox.yaml (configs/v3.yaml with every output root and data/raw under <E2E>/sb, light
  Phase-2 settings, n_jobs <= 2; the hash-locked clean_test block is not touched)
- raw sources copied (SRDB, Natural Earth, COSORE checkout) into <E2E>/sb/raw
- WorldClim: 19 synthetic 0.25-degree GeoTIFFs (land from ne_50m_land; ocean = WorldClim's nodata -3.4e38),
  packed into wc2.1_2.5m_bio.zip with a matching .source.json sidecar, so the real fetch_worldclim stage
  extracts and records them without a request
- SoilGrids: 8 synthetic 0.5-degree int16 GeoTIFFs with matching sidecars (fetch_soilgrids then makes no request)
Nothing is written under /home/user/MSHI.
"""
import copy
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
import numpy as np
import yaml

from mshi.config import load_config, canonical_sha256
from mshi.data import rasters as R
from mshi.io import sha256_file, write_json

E2E = Path(sys.argv[1])
SB = E2E / "sb"
REPO = Path("/home/user/MSHI")

cfg0 = load_config()
data = copy.deepcopy(cfg0.data)
for root in ("raw", "interim", "derived", "results", "figures"):
    data["paths"][root] = str(SB / root)
# light settings (n_jobs <= 2)
p2 = data["phase2"]
p2["bootstrap"]["n"] = 200
p2["transfer"]["rf"].update(n_estimators=25, n_jobs=2)
p2["within"]["seeds"] = [42, 43]
p2["within"]["knndm"]["max_pred_points"] = 1500
p2["noise_ceiling"].update(n_boot=10, n_jobs=2)
p2["aoa"]["perm_repeats"] = 2
p2["us_r2"]["xgb_seed_spread"] = [0, 3]
(E2E).mkdir(parents=True, exist_ok=True)
cfg_path = E2E / "v3_sandbox.yaml"
cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
print("config:", cfg_path)

cfg = load_config(cfg_path)
raw = cfg.path("raw")
raw.mkdir(parents=True, exist_ok=True)
# --- pinned sources (copies, read-only use of the repository's data/raw)
for sub in ("srdb", "naturalearth"):
    if not (raw / sub).exists():
        shutil.copytree(REPO / "data/raw" / sub, raw / sub)
cos = raw / "cosore" / "02f32e8e"
if not cos.exists():
    cos.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-a", str(REPO / "data/raw/cosore/02f32e8e"), str(cos)], check=True)

# --- synthetic WorldClim
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin

w = cfg["sources"]["worldclim"]
deg = 0.25
nx, ny = int(360 / deg), int(180 / deg)
tr = from_origin(-180.0, 90.0, deg, deg)
land = gpd.read_file(raw / "naturalearth/v5.1.2/ne_50m_land.geojson")
mask = rasterize(((g, 1) for g in land.geometry), out_shape=(ny, nx), transform=tr, fill=0, all_touched=True,
                 dtype="uint8").astype(bool)
lon = -180 + deg / 2 + deg * np.arange(nx)
lat = 90 - deg / 2 - deg * np.arange(ny)
LON, LAT = np.meshgrid(lon, lat)
A = np.abs(LAT)
bio = {}
bio[1] = 27 - 0.5 * A + 3 * np.sin(np.radians(LON) * 2)                       # MAT
bio[2] = 8 + 4 * np.cos(np.radians(LON))                                      # diurnal range
bio[3] = 40 + 20 * np.cos(np.radians(LAT) * 2)
bio[4] = 100 + 25 * A + 50 * (1 + np.sin(np.radians(LON)))                    # temp seasonality
bio[5] = bio[1] + 10 + 0.1 * A
bio[6] = bio[1] - 5 - 0.3 * A
bio[7] = bio[5] - bio[6]
bio[8] = bio[1] + 3
bio[9] = bio[1] - 3
bio[10] = bio[1] + 5
bio[11] = bio[1] - 6
bio[12] = 200 + 1800 * np.exp(-(LAT / 25) ** 2) + 300 * (1 + np.sin(np.radians(LON) * 3))   # MAP > 0
bio[13] = bio[12] * 0.2
bio[14] = bio[12] * 0.02
bio[15] = 30 + 50 * np.abs(np.sin(np.radians(LAT) * 4))
bio[16] = bio[12] * 0.45
bio[17] = bio[12] * 0.08
bio[18] = bio[12] * 0.3
bio[19] = bio[12] * 0.1
NODATA = -3.4e38
wdir = R.worldclim_dir(cfg)
wdir.mkdir(parents=True, exist_ok=True)
stage = E2E / "wc_build"
stage.mkdir(exist_ok=True)
tifs = []
for i in range(1, 20):
    a = np.where(mask, bio[i], NODATA).astype("float32")
    p = stage / w["file_pattern"].format(i=i)
    with rasterio.open(p, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", crs="EPSG:4326",
                       transform=tr, nodata=NODATA, compress="deflate") as dst:
        dst.write(a, 1)
    tifs.append(p)
zpath = wdir.parent / w["url"].rsplit("/", 1)[-1]
with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for p in tifs:
        z.write(p, p.name)
zside = zpath.with_name(zpath.name + ".source.json")
write_json({"request_sha256": R._request_sha256(w, R.WORLDCLIM_ZIP_REQUEST), "url": w["url"],
            "sha256": {zpath.name: sha256_file(zpath)}}, zside)
print("worldclim zip:", zpath, sha256_file(zpath))

# --- synthetic SoilGrids
sg = cfg["sources"]["soilgrids"]
d2 = 0.5
nx2, ny2 = int(360 / d2), int(180 / d2)
tr2 = from_origin(-180.0, 90.0, d2, d2)
mask2 = rasterize(((g, 1) for g in land.geometry), out_shape=(ny2, nx2), transform=tr2, fill=0, all_touched=True,
                  dtype="uint8").astype(bool)
lat2 = 90 - d2 / 2 - d2 * np.arange(ny2)
L2 = np.repeat(lat2[:, None], nx2, axis=1)
base = {"soc": 300, "nitrogen": 200, "phh2o": 60, "clay": 250, "sand": 400, "silt": 350, "bdod": 130, "cec": 200}
for k, v in enumerate(sg["variables"]):
    a = np.where(mask2, base[v] + 50 * np.cos(np.radians(L2) * (k + 1)), 0).astype("int16")
    p = R.soilgrids_path(cfg, v)
    p.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(p, "w", driver="GTiff", height=ny2, width=nx2, count=1, dtype="int16", crs="EPSG:4326",
                       transform=tr2, compress="deflate") as dst:
        dst.write(a, 1)
    params = R.soilgrids_params(sg, v)
    request = canonical_sha256({"version": sg["version"], "wcs_url": sg["wcs_url"], "params": params, "file": p.name})
    write_json({"request_sha256": request, "params": params, "sha256": {p.name: sha256_file(p)}},
               p.with_name(p.name + ".source.json"))
print("soilgrids ok")
print("land cells (0.25):", int(mask.sum()))
