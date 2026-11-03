"""`make smoke` (python -m mshi.run --stage all --smoke) once the gridded sources are reachable: the smoke run
skips clean_test ("the locked test and targets need the full site set") but runs europe_geo_sensitivity, whose
control compares the 50-site subset's 'full locked Europe set' with the locked primary metrics. Emulated with
the real site build + smoke_subset, and synthetic features recorded as the outputs of a current features
result (as tests/test_smoke.py does). Nothing real is scored: the target is synthetic."""
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
from mshi.io import write_result, write_table  # noqa: E402
from mshi.run import run  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
SB = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb/smoke_eg")
if SB.exists():
    shutil.rmtree(SB)
cfg = load_config()
data = copy.deepcopy(cfg.data)
sand = Config(data, source=cfg.source, out_root=SB)        # a smoke run: out_root set, raw = repo data/raw (read)
sand.path("derived").mkdir(parents=True)
for name in ("cosore_annual", "cosore_annual_analysis"):
    csv = sand.path("derived", f"{name}.csv")
    shutil.copy(cfg.path("derived", f"{name}.csv"), csv)
    write_result(sand, {"seeded_from": f"data/derived/{name}.csv"}, f"{name}.json", outputs=[csv])
print("site build + smoke_subset exit:", run(["build_sites", "build_sites_analysis", "smoke_subset"], sand))

rng = np.random.default_rng(0)
outs = []
for tag in ("qc", "repo"):
    st = pd.read_parquet(sand.path("derived", f"sites_v3_{tag}.parquet"))
    d = st[["site_id", "lat", "lon", "continent", "country"]].copy()
    cols = set().union(*map(set, cfg["clean_test"]["locked"]["sets"].values()))
    for c in sorted(cols):
        d[c] = rng.gamma(3.0, 10.0, len(d))
    d["log_rs"] = 5.5 + 0.02 * d.bio01 + 0.1 * np.log(d.bio12) + rng.normal(0, 0.3, len(d))   # synthetic target
    sand.path("interim").mkdir(parents=True, exist_ok=True)
    outs.append(write_table(d, sand.path("interim", f"features_v3_{tag}.parquet")))
write_result(sand, {"synthetic": True}, "features.json", outputs=outs)
print("smoke subset: Asia", int((d.continent == "Asia").sum()), "Europe", int((d.continent == "Europe").sum()))

code = run(["europe_geo_sensitivity"], sand)
print("europe_geo_sensitivity in a smoke run: exit code", code)
for line in sand.path("results", "run_log.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r["stage"] == "europe_geo_sensitivity":
        print("run-log record:", r["stage"], "|", r["status"][:200], "| smoke:", r["smoke"], "| exploratory:",
              r["exploratory"])
print("result written:", sand.path("results", "europe_geo_sensitivity.json").exists())
