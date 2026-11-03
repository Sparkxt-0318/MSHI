"""Area D end-to-end, step 2: a MODIS stand-in cache (data/interim/modis_points.parquet + .meta.json) for the
sandbox's point set, keyed exactly as mshi.data.modis keys a real extraction, so the real modis_points stage
reuses it without a request. At the 889 original sites NPP = committed NPP x 0.1 x (1 + noise), with the noise
chosen so the repro_checks NPP r lands inside 0.982 +- 0.01 (a stand-in for "the NPP check reproduced").
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
import numpy as np
import pandas as pd

from mshi.config import load_config
from mshi.data import modis as M
from mshi.io import read_table

cfg = load_config(Path(sys.argv[1]))
pts = M.modis_point_set(cfg)
key = M.modis_cache_key(cfg, pts.site_key)
rng = np.random.default_rng(2026)
lat = pts.lat.to_numpy(float)
npp = 300 + 500 * np.cos(np.radians(lat)) ** 2 + rng.normal(0, 30, len(pts))
lst_day = 30 - 0.5 * np.abs(lat) + rng.normal(0, 1, len(pts))
lst_night = lst_day - 10 - 0.05 * np.abs(lat)
t = pd.DataFrame({"site_key": pts.site_key, "npp": npp, "npp_n": 5, "lst_day": lst_day, "lst_day_n": 60,
                  "lst_night": lst_night, "lst_night_n": 60})
o = pd.concat([read_table(cfg, cfg.repo_path(rel)) for rel in cfg["legacy_allowlist"]], ignore_index=True)
o["site_key"] = M.site_key(o.latitude, o.longitude, cfg["features"]["site_key_round"]).values
o = o.dropna(subset=["npp"]).drop_duplicates("site_key")
noise = rng.normal(0, 0.082, len(o))
val = dict(zip(o.site_key, o.npp.to_numpy(float) * 0.1 * (1 + noise) + 0 * noise))
t["npp"] = [val.get(k, v) for k, v in zip(t.site_key, t.npp)]
both = o.site_key.isin(t.site_key)
r = np.corrcoef(o.npp[both], [val[k] for k in o.site_key[both]])[0, 1]
print("points", len(t), "r at original sites", round(float(r), 4))
rec = {"n_points": int(len(pts)), "n_tiles": 0, "n_planned_reads": 0, "n_raster_reads": 0, "n_failed_reads": 0,
       "failed_reads": [], "cache_key": key, "n_catalog_gaps": 0, "catalog_gaps": [], "accepted_catalog_gaps": [],
       "lst_same_date_ties": {"n": 0, "list": []}, "npp_duplicate_years": [],
       "periods_outside_datetime": {"n": 0, "list": []},
       "missing": {c: int(t[c].isna().sum()) for c in ["npp", "lst_day", "lst_night"]},
       "STAND_IN": "synthetic MODIS values written by the area-D reviewer's sandbox (not an extraction)"}
M.write_modis_cache(cfg, t, key, rec)
print("written", M._paths(cfg))
