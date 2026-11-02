"""D-P1-18 claim: after a reproduction FAIL, do later stages still run? Append a fake Phase-2 stage after
repro_checks (as a future stage without an explicit dependency would be) and run with a failing target."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.io import write_result
import mshi.run as R
S = Path(sys.argv[1]); shutil.rmtree(S, ignore_errors=True)
base = load_config()
d = copy.deepcopy(base.data)
for k in ("raw", "interim", "derived", "results", "figures"):
    d["paths"][k] = str(S / k)
d["reproduction_targets"]["srdb_repo_filter_records"]["value"] = 4770
c = Config(d, source=base.source)
for f in ["build_sites.json", "cosore_annual.json"]:
    o = json.loads(base.path("results", f).read_text()); o.pop("_provenance"); write_result(c, o, f)
ran = []
orig = R._stages
R._stages = lambda: orig() + [R.Stage("phase2_transfer", lambda cfg: ran.append("phase2") or {"ok": 1}, ["build_sites"])]
code = R.run(["repro_checks", "phase2_transfer"], c)
recs = [json.loads(l) for l in (S / "results" / "run_log.jsonl").read_text().splitlines()]
print("exit", code, [(r["stage"], r["status"][:40]) for r in recs], "phase2 ran:", ran)
