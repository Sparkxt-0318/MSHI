"""spec-06 re-check: a FAIL row through the real runner (non-smoke: absolute scratch paths, out_root None)."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.io import write_result
import mshi.run as R
S = Path(sys.argv[1]); shutil.rmtree(S, ignore_errors=True)
base = load_config()
def mk(edit=None):
    d = copy.deepcopy(base.data)
    for k in ("raw", "interim", "derived", "results", "figures"):
        d["paths"][k] = str(S / k)
    if edit: edit(d)
    return Config(d, source=base.source)
for target, name in [(4771, "pass"), (4770, "fail")]:
    c = mk(lambda d: d["reproduction_targets"]["srdb_repo_filter_records"].__setitem__("value", target))
    for f in ["build_sites.json", "cosore_annual.json"]:
        o = json.loads(base.path("results", f).read_text()); o.pop("_provenance")
        write_result(c, o, f)
    code = R.run(["repro_checks"], c)
    rec = [json.loads(l) for l in (S / "results" / "run_log.jsonl").read_text().splitlines()][-1]
    md = (S / "results" / "reproduction_check.md").read_text().splitlines()[3]
    print(name, "exit", code, "| status:", rec["status"][:90], "|", md)
