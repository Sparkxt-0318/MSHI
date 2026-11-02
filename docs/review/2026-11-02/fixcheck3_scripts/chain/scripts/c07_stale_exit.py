"""Re-check guards-new-stale-rows-exit-0: an all-STALE table, through run() and the CLI; FAIL + STALE."""
import sys, json, copy, logging, io as _io
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import yaml
import cc
from mshi.run import run, main
from mshi.io import write_result
base = cc.SCR / "work" / "c07"
cc.reset(base)
buf = _io.StringIO()
h = logging.StreamHandler(buf); h.setLevel(logging.INFO)
logging.getLogger("mshi").addHandler(h); logging.getLogger("mshi").setLevel(logging.INFO)
a = cc.full_sand("s", base=base)
cc.seed_committed(a)
code = run(["repro_checks"], a)
print("control: exit", code, cc.statuses(a), cc.summary(a))
edit = lambda d: d["smoke"].__setitem__("seed", 1)
b = cc.full_sand("s", edit, base=base)
n = len(cc.runlog(b))
buf.truncate(0); buf.seek(0)
code = run(["repro_checks"], b)
print("after unrelated config edit: exit", code, cc.statuses(b, n), cc.summary(b))
print("console:", [l for l in buf.getvalue().splitlines() if "repro_checks" in l][:2])
print("md written:", "| STALE |" in b.path("results", "reproduction_check.md").read_text())
# CLI with an edited config file (absolute scratch paths)
yml = base / "edited.yaml"
yml.write_text(yaml.safe_dump(b.data, sort_keys=False))
n = len(cc.runlog(b))
code = main(["--stage", "repro_checks", "--config", str(yml)])
print("CLI exit", code, cc.statuses(b, n))
# FAIL + STALE: build_sites.json re-stamped under a config whose srdb target fails; cosore_annual.json left stale
f = lambda d: d["reproduction_targets"]["srdb_repo_filter_records"].__setitem__("value", 4770)
c = cc.full_sand("s", f, base=base)
cc.seed_committed(c, names=("build_sites.json",))
n = len(cc.runlog(c))
code = run(["repro_checks"], c)
print("FAIL + STALE: exit", code, cc.statuses(c, n), cc.summary(c))
