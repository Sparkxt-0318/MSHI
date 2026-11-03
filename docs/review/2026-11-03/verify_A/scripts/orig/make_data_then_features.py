"""`make data` then `make features` (the Makefile's partial targets) on a fresh machine: does modis_points (which
now also needs the analysis build, D-P2-6) find its inputs? Fetch stages are left out (pinned files are read from
the repo's data/raw, read-only); the stage lists are otherwise the Makefile's."""
import json, logging, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/scripts/orig")
from sbcfg import sandbox_cfg
from mshi.run import run
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
cfg = sandbox_cfg("mkdata")
print("make data (minus fetches): exit", run(["cosore_annual", "build_sites", "repro_checks"], cfg))
print("make features (minus fetches): exit", run(["modis_points", "features"], cfg))
for line in cfg.path("results", "run_log.jsonl").read_text().splitlines():
    r = json.loads(line)
    print("  ", r["stage"], "|", r["status"][:170])
