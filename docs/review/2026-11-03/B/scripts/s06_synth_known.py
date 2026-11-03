"""End-to-end synthetic known-answer run of transfer_matrix + within_continent (real code, real kNNDM; fake climate
grid = the Natural-Earth stand-in; synthetic climate and outcomes on the real analysis QC site coordinates).
log Rs = 4.5 + 0.07 bio01 + 0.35 ln bio12 + delta[continent] + N(0, 0.25^2). Usage: s06_synth_known.py OUTDIR"""
import sys, json, time, types, copy
sys.path.insert(0, "/home/user/MSHI"); sys.path.insert(0, "/home/user/MSHI/tests")
from pathlib import Path
import numpy as np, pandas as pd
import mshi.analysis as analysis_pkg
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
from mshi.analysis import knndm as KN
from mshi.io import write_result, write_table, require_current

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
DELTA = {"Asia": 0.0, "Europe": 0.35, "North America": -0.25, "South America": 0.15, "Africa": -0.15, "Oceania": 0.05}
SIG = 0.25

def edit(data):
    tr = data["phase2"]["transfer"]
    tr["rf"].update(n_estimators=30, n_jobs=2)
    data["clean_test"]["locked"]["xgb"]  # unchanged: the real XGB parameters (n_jobs 2)
    data["phase2"]["bootstrap"]["n"] = 300

base = load_config()
data = copy.deepcopy(base.data)
data["paths"]["raw"] = str(OUT / "raw")
edit(data)
cfg = Config(data, source=base.source, out_root=OUT / "out")

rng = np.random.default_rng(20261103)
s = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet")[["site_id", "lon", "lat", "continent_geo"]].copy()
n = len(s)
s["bio01"] = 28 - 0.45 * s.lat.abs() + rng.normal(0, 2.0, n)
s["bio12"] = np.exp(rng.normal(6.6, 0.5, n))
for c in ("bio04", "bio05", "bio06", "bio14", "bio15", "bio17"):
    s[c] = rng.normal(50, 10, n)
s["truth_clim"] = 4.5 + 0.07 * s.bio01 + 0.35 * np.log(s.bio12)
s["log_rs"] = s.truth_clim + s.continent_geo.map(DELTA) + rng.normal(0, SIG, n)
s["continent"] = "locked-not-used"
paths = [write_table(s.drop(columns="truth_clim"), cfg.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
write_result(cfg, {"synthetic": True}, "features_analysis.json", outputs=paths)
write_result(cfg, {"synthetic": True}, "fetch_worldclim.json")
grid = pd.read_parquet(Path(__file__).resolve().parent.parent / "work" / "ne_grid_0p5.parquet")

def climate_grid(c, deg, with_continent=True):
    require_current(c, "fetch_worldclim.json")
    return grid[["lon", "lat", "continent_geo", "area_km2"]].copy()
T.climate_grid = climate_grid
t0 = time.time()
T.transfer_matrix(cfg)
t1 = time.time()
T.within_continent(cfg)
t2 = time.time()
print(f"transfer_matrix {t1-t0:.0f}s, within_continent {t2-t1:.0f}s")
s.to_parquet(OUT / "truth.parquet", index=False)
