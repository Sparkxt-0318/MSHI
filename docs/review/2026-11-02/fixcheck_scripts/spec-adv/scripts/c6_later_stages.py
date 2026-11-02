"""Claim 6: after repro_checks raises ReproductionFailure, does run() still run stages ordered after it?

Usage: python -B c6_later_stages.py <sandbox_dir>
Sandbox paths are absolute (out_root None, so run() does not treat it as a smoke run).
"""
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import write_result  # noqa: E402
import mshi.run as R  # noqa: E402

S = Path(sys.argv[1])
shutil.rmtree(S, ignore_errors=True)
base = load_config()
d = copy.deepcopy(base.data)
for k in ("raw", "interim", "derived", "results", "figures"):
    d["paths"][k] = str(S / k)
d["reproduction_targets"]["srdb_repo_filter_records"]["value"] = 4770      # a target the build misses
c = Config(d, source=base.source)
for f in ["build_sites.json", "cosore_annual.json"]:
    o = json.loads(base.path("results", f).read_text())
    o.pop("_provenance")
    write_result(c, o, f)

ran = []
orig = R._stages
R._stages = lambda: orig() + [
    R.Stage("phase2_nodep", lambda cfg: ran.append("phase2_nodep") or {"ok": 1}, []),
    R.Stage("phase2_sites", lambda cfg: ran.append("phase2_sites") or {"ok": 1}, ["build_sites"]),
    R.Stage("phase2_gated", lambda cfg: ran.append("phase2_gated") or {"ok": 1}, ["repro_checks"]),
]
print("pipeline order:", [s.name for s in R._stages()])
code = R.run(["phase2_gated", "phase2_sites", "phase2_nodep", "repro_checks"], c)
recs = [json.loads(x) for x in (S / "results" / "run_log.jsonl").read_text().splitlines()]
print("exit", code)
for r in recs:
    print("  ", r["stage"], "->", r["status"][:70])
print("stage functions that ran after the FAIL:", ran)
