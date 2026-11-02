"""Render the NPP reproduction rows from a SYNTHETIC MODIS table (sandbox out_root) to check the method note,
n and the INFO row. The v3 NPP values are synthetic; the r printed here means nothing."""
import copy, json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import Config, load_config
from mshi.io import read_table, write_json, write_result, write_table
from mshi.data.modis import modis_cache_key, site_key
from mshi.analysis.repro_checks import repro_checks
cfg = load_config()
OUT = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/fidelity/npp/out"
sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=OUT)
o = pd.concat([read_table(sand, sand.repo_path(r)) for r in sand["legacy_allowlist"]], ignore_index=True)
keys = site_key(o.latitude, o.longitude, 5)
rng = np.random.default_rng(5)
v3 = np.where(o.npp.notna(), o.npp * 0.1 * (1 + rng.normal(0, .05, len(o))), rng.uniform(100, 900, len(o)))
v3[:7] = np.nan                                    # a few sites missing in v3
t = pd.DataFrame({"site_key": keys.values, "npp": v3, "npp_n": 5, "lst_day": 10.0, "lst_day_n": 60,
                  "lst_night": 0.0, "lst_night_n": 60})
write_table(t, sand.path("interim", "modis_points.parquet"))
rec = {"n_points": len(t), "n_failed_reads": 0, "failed_reads": []}
write_json({"key": modis_cache_key(sand, t.site_key), "record": rec}, sand.path("interim", "modis_points.meta.json"))
write_result(sand, rec, "modis_points.json")
print(repro_checks(sand))
for r in json.load(open(f"{OUT}/results/reproduction_check.json"))["rows"][-2:]:
    print(json.dumps(r))
print(json.load(open(f"{OUT}/results/reproduction_check.json"))["npp_check"])
print(open(f"{OUT}/results/reproduction_check.md").read().splitlines()[-4:-2])
