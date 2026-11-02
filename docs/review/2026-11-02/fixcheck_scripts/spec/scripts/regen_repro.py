"""Regenerate results/reproduction_check.{json,md} from the committed results + the 13:30 invocation statuses,
in a scratch out_root with the unmodified config (same config hash). Compare with the committed files."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.analysis.repro_checks import repro_checks

out = Path(sys.argv[1]); shutil.rmtree(out, ignore_errors=True)
base = load_config()
c = Config(copy.deepcopy(base.data), source=base.source, out_root=out)
res = c.path("results"); res.mkdir(parents=True)
src = base.path("results")
for f in src.iterdir():
    if f.name not in ("reproduction_check.json", "reproduction_check.md"):
        shutil.copy(f, res / f.name)
recs = [json.loads(l) for l in (src / "run_log.jsonl").read_text().splitlines()]
last_inv = [r for r in recs if r.get("git_commit", "").startswith("b74e590")]
status = {r["stage"]: r["status"] for r in last_inv if r["stage"] != "repro_checks"}
c.invocation = {"stages": [r["stage"] for r in last_inv], "status": status}
print("config hash equal:", c.sha256() == base.sha256())
s = repro_checks(c)
print("summary", s)
a = json.loads((res / "reproduction_check.json").read_text()); b = json.loads((src / "reproduction_check.json").read_text())
print("json identical:", a == b, "| bytes identical:", (res / "reproduction_check.json").read_bytes() == (src / "reproduction_check.json").read_bytes())
print("md identical:", (res / "reproduction_check.md").read_text() == (src / "reproduction_check.md").read_text())
# repro-only invocation (make repro) on the committed state
c2 = Config(copy.deepcopy(base.data), source=base.source, out_root=out)
c2.invocation = {"stages": ["repro_checks"], "status": {}}
s2 = repro_checks(c2)
print("make-repro summary", s2)
for r in json.loads((res / "reproduction_check.json").read_text())["rows"][17:]:
    print("  ", r["status"], "|", r["quantity"][:50], "|", r["note"])
