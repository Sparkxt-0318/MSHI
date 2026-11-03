"""`make phase2` (repro_checks + the Phase-2 stages in one invocation) vs a separate invocation, when a row of a
group the noise ceiling does not need FAILs (e.g. the NPP check after the network opens)."""
import copy, sys, logging
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
from mshi.io import write_result
import mshi.run as R
from mshi.run import Stage
from mshi.analysis.repro_checks import ReproductionFailure
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
base = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb/gate_phase2")
cfg0 = load_config(); d = copy.deepcopy(cfg0.data)
for root in ("raw", "interim", "derived", "results", "figures"):
    d["paths"][root] = str(base / root)
cfg = Config(d, source=cfg0.source)
ran = []
rows = ([{"quantity": f"QC sites: {i}", "status": "PASS", "group": "site_build"} for i in range(17)]
        + [{"quantity": "Locked test: Europe R²", "status": "PASS", "group": "locked_test"},
           {"quantity": "NPP r vs committed NPP (original 889 sites)", "status": "FAIL", "group": "npp"}])
def fake_repro(c):        # as repro_checks: writes the (current) table, then raises on a FAIL row
    write_result(c, {"rows": rows, "summary": {"PASS": 18, "FAIL": 1}}, "reproduction_check.json")
    raise ReproductionFailure("1 reproduction target(s) outside tolerance: ['NPP r ...']")
R._stages = lambda: [Stage("repro_checks", fake_repro),
                     Stage("noise_ceiling", lambda c: ran.append("noise_ceiling") or {}, [], needs=("site_build",),
                           exploratory=True)]
print("make phase2-like invocation [repro_checks, noise_ceiling]: exit", R.run(["repro_checks", "noise_ceiling"], cfg),
      "; noise_ceiling ran:", "noise_ceiling" in ran)
print("separate invocation [noise_ceiling]: exit", R.run(["noise_ceiling"], cfg), "; noise_ceiling ran:", "noise_ceiling" in ran)
import json
for line in cfg.path("results", "run_log.jsonl").read_text().splitlines():
    r = json.loads(line); print("  run log:", r["stage"], "|", r["status"][:120])
