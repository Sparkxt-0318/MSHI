"""A-5 independent check, through the CLI entry point `mshi.run.main` with the Makefile's own stage lists
(`make -n data|analysis|features`), full (non-smoke) sandboxes with absolute scratch paths, data/raw read only.
Network stages stood in for: fetch_* record results, COSORE tables seeded from data/derived, synthetic rasters,
MODIS extraction faked (check_reachable / extract_points). Everything else is the real code.

(a1) fresh sandbox: make data; make features
(a2) the state the repo is in now (results from older code): build_sites_analysis.json produced by other code;
     make data; make features; then make analysis; make features
(b)  `make all` (main --stage all) with build_sites_analysis failing (a different failure point from the
     reviewer's, who made cosore_annual_analysis fail)
"""
import copy
import json
import logging
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, "/home/user/MSHI")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
import mshi.run as R  # noqa: E402
from mshi.config import load_config  # noqa: E402
from mshi.io import _read_result, write_json, write_result  # noqa: E402
import mshi.data.fetch as FE  # noqa: E402
import mshi.data.cosore as CO  # noqa: E402
import mshi.data.rasters as RA  # noqa: E402
import mshi.data.features as F  # noqa: E402
import mshi.data.modis as MO  # noqa: E402
import mshi.data.sites_analysis as SA  # noqa: E402
import mshi.netutil as N  # noqa: E402

SCR = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/a5")
repo_cfg = load_config()


def target_args(t):
    out = subprocess.run(["make", "-n", t], cwd="/home/user/MSHI", capture_output=True, text=True).stdout
    args = shlex.split(out.replace("\\\n", " "))
    return args[args.index("mshi.run") + 1:]


def new_sandbox(name):
    base = SCR / name
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    d = yaml.safe_load(open("/home/user/MSHI/configs/v3.yaml"))
    for root in ("interim", "derived", "results", "figures"):
        d["paths"][root] = str(base / root)
    d["paths"]["raw"] = "/home/user/MSHI/data/raw"
    d["phase2"]["noise_ceiling"].update(n_boot=4, n_jobs=1)
    f = base / "cfg.yaml"
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    return f


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
        write_result(cfg, {"seeded_from": f"data/derived/{name}.csv", "n_sites": len(pd.read_csv(csv))},
                     f"{name}.json", outputs=[csv])
        return {"seeded": name}
    return f


FE.fetch_srdb, FE.fetch_cosore, FE.fetch_naturalearth = (rec_fetch("fetch_srdb"), rec_fetch("fetch_cosore"),
                                                          rec_fetch("fetch_naturalearth"))
CO.cosore_annual, CO.cosore_annual_analysis = seed_cosore("cosore_annual"), seed_cosore("cosore_annual_analysis")
paths = {}


def _wgs(path, values, dtype="float32"):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", width=360, height=180, count=1, dtype=dtype, crs="EPSG:4326",
                       transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


def rasters(cfg):
    paths.clear()
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    rdir = cfg.path("interim", "synthetic_rasters")
    rdir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 20):
        _wgs(rdir / f"wc{i}.tif", 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2)
        paths[("wc", i)] = rdir / f"wc{i}.tif"
    for k in cfg["sources"]["soilgrids"]["variables"]:
        _wgs(rdir / f"{k}.tif", np.full((180, 360), 120), dtype="int16")
        paths[("sg", k)] = rdir / f"{k}.tif"


def fake_wc(cfg):
    rasters(cfg)
    write_result(cfg, {"synthetic": True}, "fetch_worldclim.json", outputs=[paths[("wc", i)] for i in range(1, 20)])
    return {}


def fake_sg(cfg):
    if not paths:
        rasters(cfg)
    write_result(cfg, {"synthetic": True}, "fetch_soilgrids.json",
                 outputs=[paths[("sg", k)] for k in cfg["sources"]["soilgrids"]["variables"]])
    return {}


RA.fetch_worldclim, RA.fetch_soilgrids = fake_wc, fake_sg
F.worldclim_path = lambda c, i: paths[("wc", i)]
F.soilgrids_path = lambda c, v: paths[("sg", v)]
N.check_reachable = lambda *a, **k: None
MO.extract_points = lambda p, m: (pd.DataFrame({"site_key": p.site_key.values, "npp": 400.0, "npp_n": 5,
                                                "lst_day": 20.0, "lst_day_n": 60, "lst_night": 5.0, "lst_night_n": 60}),
                                  {"n_jobs": 1, "n_reads": 1, "n_tiles": 1, "failed_reads": [], "catalog_gaps": [],
                                   "accepted_catalog_gaps": [], "lst_same_date_ties": [], "npp_duplicate_years": [],
                                   "periods_outside_datetime": []})


def statuses(cfgfile, n):
    c = load_config(cfgfile)
    recs = [json.loads(x) for x in c.path("results", "run_log.jsonl").read_text().splitlines()][-n:]
    return [(r["stage"], r["status"][:130]) for r in recs]


def make(cfgfile, target, show=True):
    args = target_args(target)
    code = R.main(args + ["--config", str(cfgfile)])
    n = sum(1 for a in args if a != "--stage")
    if show:
        print(f"   make {target:9s} -> exit {code}")
        for s, st in statuses(cfgfile, n):
            print(f"        {s:22s} {st}")
    return code


print("Makefile stage lists:", {t: [a for a in target_args(t) if a != "--stage"] for t in ("data", "analysis", "features")})
print("(a1) fresh sandbox")
f1 = new_sandbox("a1")
make(f1, "data")
make(f1, "features")

print("(a2) build_sites_analysis.json produced by other code (the repo's state after ec43c6c)")
f2 = new_sandbox("a2")
make(f2, "data", show=False)
make(f2, "analysis", show=False)
c2 = load_config(f2)
obj, _ = _read_result(c2, "build_sites_analysis.json")
obj["_provenance"]["code_sha256"] = "0" * 64                  # as a result from the previous commit's code
write_json(obj, c2.path("results", "build_sites_analysis.json"))
make(f2, "data")
make(f2, "features")
make(f2, "analysis")
make(f2, "features")

print("(b) make all with build_sites_analysis failing")
f3 = new_sandbox("b")
real_bsa = SA.build_sites_analysis


def boom(cfg):
    raise RuntimeError("simulated failure in the exploratory analysis build")


SA.build_sites_analysis = boom
code = R.main(["--stage", "all", "--config", str(f3)])
SA.build_sites_analysis = real_bsa
print("   make all -> exit", code)
for s, st in statuses(f3, 22):
    print(f"        {s:24s} {st}")
c3 = load_config(f3)
rc, _ = _read_result(c3, "reproduction_check.json")
print("   reproduction table:", rc["summary"])
for row in rc["rows"]:
    if row["status"] != "PASS":
        print(f"        {row['group']:11s} {row['status']:8s} {row['quantity'][:55]:55s} | {row['note'][:90]}")
