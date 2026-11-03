"""A-3 independent check with the REAL stages (the reviewer used stand-in stages): full sandbox (not a smoke run;
all outputs in scratch; data/raw read only). Real build_sites, build_sites_analysis, modis_points (extraction
faked: NPP values uncorrelated with the committed NPP, so the real repro_checks gives an NPP FAIL), real
repro_checks and real noise_ceiling (light: n_boot 4, n_jobs 1).

Invocation A = what `make phase2` / `make all` do after repro_checks: [repro_checks, noise_ceiling].
Invocation B = the noise ceiling alone, against the table invocation A wrote.
"""
import copy
import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/MSHI")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import _read_result, write_result  # noqa: E402
import mshi.data.modis as MO  # noqa: E402
import mshi.netutil as N  # noqa: E402
import mshi.run as R  # noqa: E402

SB = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/a3_real")
if SB.exists():
    shutil.rmtree(SB)
cfg0 = load_config()
d = copy.deepcopy(cfg0.data)
for root in ("interim", "derived", "results", "figures"):
    d["paths"][root] = str(SB / root)
d["paths"]["raw"] = str(Path("/home/user/MSHI/data/raw"))          # read only (SRDB CSV, Natural Earth)
d["phase2"]["noise_ceiling"].update(n_boot=4, n_jobs=1)
cfg = Config(d, source=cfg0.source)
cfg.path("derived").mkdir(parents=True)
for name in ("cosore_annual", "cosore_annual_analysis"):
    csv = cfg.path("derived", f"{name}.csv")
    shutil.copy(cfg0.path("derived", f"{name}.csv"), csv)
    write_result(cfg, {"seeded_from": f"data/derived/{name}.csv", "n_sites": len(pd.read_csv(csv))}, f"{name}.json",
                 outputs=[csv])
print("site builds:", R.run(["build_sites", "build_sites_analysis"], cfg))

N.check_reachable = lambda *a, **k: None
rng = np.random.default_rng(123)


def fake_extract(p, m):
    out = pd.DataFrame({"site_key": p.site_key.values, "npp": rng.uniform(100, 900, len(p)), "npp_n": 5,
                        "lst_day": 20.0, "lst_day_n": 60, "lst_night": 5.0, "lst_night_n": 60})
    return out, {"n_jobs": 1, "n_reads": 1, "n_tiles": 1, "failed_reads": [], "catalog_gaps": [],
                 "accepted_catalog_gaps": [], "lst_same_date_ties": [], "npp_duplicate_years": [],
                 "periods_outside_datetime": []}


MO.extract_points = fake_extract
print("modis_points:", R.run(["modis_points"], cfg))

codeA = R.run(["repro_checks", "noise_ceiling"], cfg)
rc, _ = _read_result(cfg, "reproduction_check.json")
print("invocation A [repro_checks, noise_ceiling]: exit", codeA, "| table summary", rc["summary"])
for r in rc["rows"]:
    if r["status"] != "PASS":
        print(f"    row {r['group']:11s} {r['status']:8s} {r['quantity'][:60]} v3={r['v3']}")
print("    gate the stored table gives noise_ceiling now:", R._gate_status(cfg, {}, [], ("site_build",)))
codeB = R.run(["noise_ceiling"], cfg)
print("invocation B [noise_ceiling]: exit", codeB)
for line in cfg.path("results", "run_log.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r["stage"] in ("repro_checks", "noise_ceiling"):
        print(f"  run log: {r['stage']:14s} invocation={r['invocation']} {r['status'][:150]}")
print("noise_ceiling.json written:", cfg.path("results", "noise_ceiling.json").exists())
