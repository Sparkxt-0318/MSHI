"""`make smoke` (python -m mshi.run --stage all --smoke) once the gridded sources are reachable, emulated: smoke
config (out_root set), the real site builds + smoke_subset, synthetic targets, the synthetic land-masked rasters of
the 'chain' sandbox (recorded as the fetch stages' outputs), a synthetic MODIS cache for the smoke point set; then
every stage after the site build that a smoke run executes. Light settings, n_jobs 1."""
import copy
import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import _read_result, require_current, write_result, write_table  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
SCR = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb")
OUT = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/smoke_chain")
if OUT.exists():
    shutil.rmtree(OUT)
cfg0 = load_config()
d = copy.deepcopy(cfg0.data)
d["paths"]["raw"] = str(SCR / "chain" / "raw")         # symlinked pinned sources + the synthetic rasters
p2 = d["phase2"]
p2["noise_ceiling"].update(n_boot=10, n_jobs=1)
p2["transfer"]["rf"].update(n_estimators=8, grid={"min_samples_leaf": [2, 8], "max_features": [0.5, 1.0]},
                            inner_folds=3, n_jobs=1)
p2["transfer"]["xgb_light"] = {**d["clean_test"]["locked"]["xgb"], "n_estimators": 12}
p2["transfer"]["xgb_from"] = "phase2.transfer.xgb_light"
p2["within"].update(folds=2, seeds=[42, 43])
p2["within"]["knndm"].update(max_pred_points=300)
p2["bootstrap"]["n"] = 60
p2["aoa"].update(perm_repeats=2)
p2["us_r2"].update(xgb_seed_spread=[0, 1])
cfg = Config(d, source=cfg0.source, out_root=OUT)
from mshi.run import run  # noqa: E402

cfg.path("derived").mkdir(parents=True)
for name in ("cosore_annual", "cosore_annual_analysis"):
    csv = cfg.path("derived", f"{name}.csv")
    shutil.copy(cfg0.path("derived", f"{name}.csv"), csv)
    write_result(cfg, {"seeded_from": f"data/derived/{name}.csv"}, f"{name}.json", outputs=[csv])
print("build + smoke_subset exit:", run(["build_sites", "build_sites_analysis", "smoke_subset"], cfg))

rng = np.random.default_rng(11)
for prefix, rec_name, res_name in (("sites_v3", "records_v3.parquet", "build_sites.json"),
                                   ("sites_analysis", "records_analysis.parquet", "build_sites_analysis.json")):
    rp = cfg.path("derived", rec_name)
    r = pd.read_parquet(rp)
    lr = 6.4 - 0.008 * r.lat.abs() + 0.1 * np.sin(np.radians(r.lon)) + rng.normal(0, 0.35, len(r))
    r["rs"], r["log_rs"] = np.exp(lr), lr
    write_table(r, rp)
    outs = [rp]
    for tag in ("qc", "repo"):
        sp = cfg.path("derived", f"{prefix}_{tag}.parquet")
        s = pd.read_parquet(sp)
        g = r.dropna(subset=[f"site_id_{tag}"]).groupby(f"site_id_{tag}").log_rs
        s["log_rs"], s["log_rs_sd"] = s.site_id.map(g.mean()), s.site_id.map(g.std())
        s["rs"] = np.exp(s.log_rs)
        write_table(s, sp)
        outs.append(sp)
    b, _ = _read_result(cfg, res_name)
    write_result(cfg, {**b, "synthetic_targets": True}, res_name, outputs=outs, inputs=dict(b.get("_inputs") or {}))
    require_current(cfg, res_name)

from mshi.data.rasters import soilgrids_path, worldclim_path  # noqa: E402
write_result(cfg, {"synthetic": True}, "fetch_worldclim.json", outputs=[worldclim_path(cfg, i) for i in range(1, 20)])
write_result(cfg, {"synthetic": True}, "fetch_soilgrids.json",
             outputs=[soilgrids_path(cfg, v) for v in cfg["sources"]["soilgrids"]["variables"]])
from mshi.data.modis import modis_cache_key, modis_point_set, write_modis_cache  # noqa: E402
pts = modis_point_set(cfg)
mod = pd.DataFrame({"site_key": pts.site_key.values, "npp": 300 + 3 * pts.lat.abs().values, "npp_n": 5,
                    "lst_day": 25 - 0.3 * pts.lat.abs().values, "lst_day_n": 60,
                    "lst_night": 10 - 0.3 * pts.lat.abs().values, "lst_night_n": 60})
out = write_modis_cache(cfg, mod, modis_cache_key(cfg, pts.site_key), {"n_failed_reads": 0, "synthetic": True})
write_result(cfg, {"n_failed_reads": 0, "synthetic": True}, "modis_points.json", outputs=[out],
             inputs=["build_sites.json", "build_sites_analysis.json"])

STAGES = ["features", "clean_test", "repro_checks", "noise_ceiling", "europe_geo_sensitivity", "features_analysis",
          "transfer_matrix", "within_continent", "aoa_sensitivity", "us_r2"]
code = run(STAGES, cfg)
print("smoke run of the stages after the site build: exit code", code)
last = {}
for line in cfg.path("results", "run_log.jsonl").read_text().splitlines():
    rec = json.loads(line)
    last[rec["stage"]] = rec
for s in STAGES:
    r = last.get(s)
    print(f"  {s:24s} {'(not run: excluded from smoke runs)' if r is None else r['status'][:160]}")
