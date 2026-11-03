"""A-1 independent check (different method and inputs from the reviewer's): drive the real CLI entry point
`mshi.run.main(["--stage", "all", "--smoke", "--config", <cfg>])` (full=True, the exact `make smoke` path) with
a config whose output roots are absolute scratch paths and a different smoke seed (7 instead of the config's).

Only what cannot run here is stood in for, in-process:
- fetch_* stages of pinned sources and the two COSORE stages: recorded results / the committed COSORE tables
  (avoids touching data/raw's git checkout; raw is read-only);
- fetch_worldclim / fetch_soilgrids: tiny synthetic 1-degree rasters recorded as their outputs;
- modis_points runs for real, with check_reachable and extract_points faked (synthetic values);
- features runs for real; afterwards the target column is replaced by a synthetic one (no real Europe outcome
  is scored) and features.json re-recorded with the same inputs;
- transfer_matrix, within_continent, aoa_sensitivity, us_r2 are stubbed (independent of europe_geo, heavy).
europe_geo_sensitivity, smoke_subset, build_sites, build_sites_analysis, noise_ceiling (light), features and
features_analysis are the real code.
"""
import copy
import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, "/home/user/MSHI")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SB = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/a1_cli")
if SB.exists():
    shutil.rmtree(SB)
SB.mkdir(parents=True)
src = yaml.safe_load(open("/home/user/MSHI/configs/v3.yaml"))
d = copy.deepcopy(src)
for root in ("interim", "derived", "results", "figures"):
    d["paths"][root] = str(SB / root)
d["smoke"]["seed"] = 7                       # a different subset from the reviewer's
p2 = d["phase2"]
p2["noise_ceiling"].update(n_boot=10, n_jobs=1)
cfg_file = SB / "v3_smoke_sandbox.yaml"
cfg_file.write_text(yaml.safe_dump(d, sort_keys=False))

import mshi.run as R  # noqa: E402
from mshi.config import load_config  # noqa: E402
from mshi.io import _read_result, require_current, write_result, write_table  # noqa: E402
import mshi.data.fetch as FE  # noqa: E402
import mshi.data.cosore as CO  # noqa: E402
import mshi.data.rasters as RA  # noqa: E402
import mshi.data.features as F  # noqa: E402
import mshi.data.modis as MO  # noqa: E402
import mshi.netutil as N  # noqa: E402
import mshi.analysis.transfer as TR  # noqa: E402
import mshi.analysis.aoa as AO  # noqa: E402
import mshi.analysis.us_r2 as US  # noqa: E402

repo_cfg = load_config()


def rec_fetch(name):
    def f(cfg):
        write_result(cfg, {"stand_in": name}, f"{name}.json")
        return {"stand_in": name}
    return f


def seed_cosore(name):
    def f(cfg):
        csv = cfg.path("derived", f"{name}.csv")
        csv.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo_cfg.path("derived", f"{name}.csv"), csv)
        write_result(cfg, {"seeded_from": f"data/derived/{name}.csv"}, f"{name}.json", outputs=[csv])
        return {"seeded": name}
    return f


FE.fetch_srdb, FE.fetch_cosore, FE.fetch_naturalearth = (rec_fetch("fetch_srdb"), rec_fetch("fetch_cosore"),
                                                          rec_fetch("fetch_naturalearth"))
CO.cosore_annual, CO.cosore_annual_analysis = seed_cosore("cosore_annual"), seed_cosore("cosore_annual_analysis")


def _wgs_raster(path, values, dtype="float32"):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


paths = {}


def make_rasters(cfg):
    if paths:
        return
    rng = np.random.default_rng(3)
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    rdir = cfg.path("interim", "synthetic_rasters")
    rdir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 20):
        v = 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2
        _wgs_raster(rdir / f"wc{i}.tif", v + rng.normal(0, 0.1, v.shape))
        paths[("wc", i)] = rdir / f"wc{i}.tif"
    for k in cfg["sources"]["soilgrids"]["variables"]:
        _wgs_raster(rdir / f"{k}.tif", 100 + 50 * np.cos(np.radians(lon)) ** 2, dtype="int16")
        paths[("sg", k)] = rdir / f"{k}.tif"


def fake_wc(cfg):
    make_rasters(cfg)
    write_result(cfg, {"synthetic": True}, "fetch_worldclim.json", outputs=[paths[("wc", i)] for i in range(1, 20)])
    return {"synthetic": True}


def fake_sg(cfg):
    make_rasters(cfg)
    write_result(cfg, {"synthetic": True}, "fetch_soilgrids.json",
                 outputs=[paths[("sg", k)] for k in cfg["sources"]["soilgrids"]["variables"]])
    return {"synthetic": True}


RA.fetch_worldclim, RA.fetch_soilgrids = fake_wc, fake_sg
F.worldclim_path = lambda c, i: paths[("wc", i)]
F.soilgrids_path = lambda c, v: paths[("sg", v)]
N.check_reachable = lambda *a, **k: None


def fake_extract(p, m):
    out = pd.DataFrame({"site_key": p.site_key.values, "npp": 300 + 3 * p.lat.abs().values, "npp_n": 5,
                        "lst_day": 25 - 0.3 * p.lat.abs().values, "lst_day_n": 60,
                        "lst_night": 10 - 0.3 * p.lat.abs().values, "lst_night_n": 60})
    return out, {"n_jobs": 1, "n_reads": 1, "n_tiles": 1, "failed_reads": [], "catalog_gaps": [],
                 "accepted_catalog_gaps": [], "lst_same_date_ties": [], "npp_duplicate_years": [],
                 "periods_outside_datetime": []}


MO.extract_points = fake_extract
real_features = F.features


def features_synthetic_target(cfg):
    res = real_features(cfg)
    b, _ = _read_result(cfg, "features.json")
    rng = np.random.default_rng(5)
    outs = []
    for tag in cfg["clean_test"]["variants"]:
        fp = cfg.path("interim", f"features_v3_{tag}.parquet")
        t = pd.read_parquet(fp)
        t["log_rs"] = 5.5 + 0.02 * t.bio01 + 0.1 * np.log(t.bio12) + rng.normal(0, 0.3, len(t))
        outs.append(write_table(t, fp))
    write_result(cfg, {**b, "synthetic_target": True}, "features.json", outputs=outs,
                 inputs=dict(b.get("_inputs") or {}))
    require_current(cfg, "features.json")
    return res


F.features = features_synthetic_target
stub = lambda name: (lambda cfg: {"stub": name})  # noqa: E731
TR.transfer_matrix, TR.within_continent = stub("transfer_matrix"), stub("within_continent")
AO.aoa_sensitivity, US.us_r2 = stub("aoa_sensitivity"), stub("us_r2")

code = R.main(["--stage", "all", "--smoke", "--config", str(cfg_file)])
print("python -m mshi.run --stage all --smoke  ->  exit code", code)
cfg = load_config(cfg_file)
log = cfg.path("results", "run_log.jsonl")
print("run log:", log)
for line in log.read_text().splitlines():
    r = json.loads(line)
    print(f"  {r['stage']:24s} smoke={r['smoke']} expl={r.get('exploratory')} {r['status'][:150]}")
sub = json.loads(cfg.path("results", "smoke_subset.json").read_text())
print("smoke subset (locked build, qc):", sub["sites_v3"]["qc"])
print("europe_geo_sensitivity.json written:", cfg.path("results", "europe_geo_sensitivity.json").exists())
