"""A copy of the package in scratch; a stage edits a module of the copy while it runs (simulating an edit
during a long stage); compare the run-log provenance with the result's _provenance."""
import json, os, shutil, sys
sys.dont_write_bytecode = True
SCR = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards"
W = os.path.join(SCR, "work", "t9"); shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
shutil.copytree("/home/user/MSHI/mshi", os.path.join(W, "pkg", "mshi"), ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree("/home/user/MSHI/configs", os.path.join(W, "pkg", "configs"))
sys.path.insert(0, os.path.join(W, "pkg"))
import mshi.run as R
from mshi.run import Stage
from mshi.io import write_result
from mshi.config import load_config
from pathlib import Path
import copy
from mshi.config import Config
base = load_config()
d = copy.deepcopy(base.data)
for k in ("interim", "derived", "results", "figures"):
    d["paths"][k] = os.path.join(W, "out", k)
cfg = Config(d, source=base.source)

def long_stage(c):
    p = Path(W) / "pkg" / "mshi" / "analysis" / "repro_checks.py"     # edited while the stage "computes"
    p.write_text(p.read_text() + "\n# edited during the run\n")
    out = {"value": 42}
    write_result(c, out, "long_stage.json")
    return out
R._stages = lambda: [Stage("long_stage", long_stage, [])]
print("exit", R.run(["long_stage"], cfg))
rec = json.loads(Path(W, "out", "results", "run_log.jsonl").read_text().splitlines()[-1])
res = json.loads(Path(W, "out", "results", "long_stage.json").read_text())
print("run_log code_sha256 (start of run):", rec["code_sha256"][:16])
print("result  code_sha256 (write time)  :", res["_provenance"]["code_sha256"][:16])
from mshi.io import result_staleness
print("result_staleness now (edited code on disk):", result_staleness(cfg, res))
