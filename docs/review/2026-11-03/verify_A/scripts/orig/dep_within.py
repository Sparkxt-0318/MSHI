"""run.py declares within_continent's deps as [transfer_matrix, fetch_worldclim], but the stage reads features_analysis'
outputs (mshi.analysis.transfer.analysis_sites -> require_outputs('features_analysis.json')). In an invocation
[features_analysis, within_continent] where features_analysis fails, within_continent is therefore not skipped as
'upstream not available': it runs on the previous features tables. Uses the 'chain' sandbox (gate open); the MODIS
sidecar is moved away for the run and restored afterwards."""
import json, logging, shutil, sys
sys.argv = [sys.argv[0], "chain"]
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/scripts")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
import chain_cfg as C
cfg = C.make_cfg()
from mshi.run import run
side = cfg.path("interim", "modis_points.meta.json")
shutil.move(side, side.with_suffix(".json.bak"))
try:
    code = run(["features_analysis", "within_continent"], cfg)
finally:
    shutil.move(side.with_suffix(".json.bak"), side)
print("exit code", code)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-2:]
for r in recs:
    print("  ", r["stage"], "|", r["status"][:200])
