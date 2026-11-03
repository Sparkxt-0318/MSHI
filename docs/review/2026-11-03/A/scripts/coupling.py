"""D-P2-6 coupling: modis_points (Phase-1 reproduction chain) now depends on the exploratory analysis build. If
cosore_annual_analysis or build_sites_analysis fails in `make all`, the MODIS extraction, the features, the
locked-test re-run and the NPP check are all skipped. cosore_annual_analysis is made to fail on purpose here
(monkeypatched exception); everything else is the real pipeline (no network is reached: modis_points is skipped
before any request)."""
import json, logging, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/scripts")
from sbcfg import sandbox_cfg
import mshi.run as R
from mshi.run import Stage
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
cfg = sandbox_cfg("coupling")
orig = R._stages
def patched():
    st = orig()
    for s in st:
        if s.name == "cosore_annual_analysis":
            def boom(c):
                raise RuntimeError("simulated failure of the exploratory COSORE analysis rule")
            s.func = boom
    return st
R._stages = patched
names = ["cosore_annual", "cosore_annual_analysis", "build_sites", "build_sites_analysis", "modis_points", "features",
         "clean_test", "repro_checks"]
print("exit", R.run(names, cfg))
for line in cfg.path("results", "run_log.jsonl").read_text().splitlines():
    r = json.loads(line); print("  ", r["stage"], "|", r["status"][:140])
rc = json.loads(cfg.path("results", "reproduction_check.json").read_text())
print("reproduction table:", rc["summary"])
for row in rc["rows"]:
    if row["status"] != "PASS":
        print("   ", row["status"], "|", row["quantity"], "|", row["note"][:110])
