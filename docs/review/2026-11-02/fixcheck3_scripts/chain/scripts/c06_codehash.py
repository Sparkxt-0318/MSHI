"""Re-check guards-new-code-hash-at-write-time on a git-archive copy of HEAD's mshi/ (imported from the copy):
a stage edits a module of the copy while it runs, then writes its result."""
import sys, json, logging, threading, time
PKG = sys.argv[1]
sys.path.insert(0, PKG)
import mshi
from pathlib import Path
assert Path(mshi.__file__).resolve().is_relative_to(Path(PKG).resolve())
logging.basicConfig(level=logging.ERROR)
import copy
from mshi.config import load_config, Config
import mshi.run as R
from mshi.runlog import code_sha256
from mshi.io import write_result, result_staleness, read_json
cfg = load_config()
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=out)
target = Path(PKG) / "mshi" / "analysis" / "repro_checks.py"
orig = target.read_bytes()
h0 = code_sha256()
def stage(c):
    target.write_bytes(orig + b"\n# edited by another session while the stage ran\n")
    time.sleep(0.01)
    write_result(c, {"x": 1}, "x.json")
    return {}
real = R._stages
R._stages = lambda: [R.Stage("x", stage, [])]
code = R.run(["x"], sand)
obj = read_json(sand.path("results", "x.json"))
rl = [json.loads(l) for l in sand.path("results", "run_log.jsonl").read_text().splitlines()][-1]
print("exit", code, "start hash", h0[:12], "| run_log", rl["code_sha256"][:12], "| result", obj["_provenance"]["code_sha256"][:12],
      "| on disk now", code_sha256()[:12])
print("result_staleness after the edit:", result_staleness(sand, obj))
print("invocation provenance cleared:", "provenance" not in sand.invocation)
# a downstream stage in the same run, after an upstream result was written and the code then edited
target.write_bytes(orig)
def up(c):
    write_result(c, {"u": 1}, "up.json"); return {}
def edit(c):
    target.write_bytes(orig + b"\n# edit 2\n"); return {}
def down(c):
    from mshi.io import require_current
    require_current(c, "up.json"); return {}
R._stages = lambda: [R.Stage("up", up, []), R.Stage("edit", edit, []), R.Stage("down", down, ["up"])]
n = len(sand.path("results", "run_log.jsonl").read_text().splitlines())
code = R.run(["up", "edit", "down"], sand)
st = {json.loads(l)["stage"]: json.loads(l)["status"][:110] for l in sand.path("results", "run_log.jsonl").read_text().splitlines()[n:]}
print("edit between stages: exit", code, st)
target.write_bytes(orig)
# direct call outside run(): stamps the current hash
write_result(sand, {"y": 1}, "y.json")
print("outside run():", read_json(sand.path("results", "y.json"))["_provenance"]["code_sha256"] == code_sha256())
