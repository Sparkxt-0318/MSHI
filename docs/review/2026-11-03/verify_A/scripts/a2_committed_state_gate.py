"""A-2 independent check: on the exact state that produced the committed results (code of 22dec94, results of
e34035a, extracted with `git archive` into scratch; nothing in the repo is touched), evaluate the gate the code
applied, and compare with the README's 'Run' paragraph. Read-only: no stage is run, nothing is written."""
import json
import sys
from pathlib import Path

ROOT = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/repo22")
sys.path.insert(0, str(ROOT))
import mshi  # noqa: E402
assert Path(mshi.__file__).resolve().is_relative_to(ROOT), mshi.__file__
from mshi.config import load_config  # noqa: E402
from mshi.io import _read_result, result_staleness  # noqa: E402
from mshi.run import GATE, _gate_status, _stages  # noqa: E402

cfg = load_config()
print("mshi imported from", Path(mshi.__file__).parent)
for name in ("reproduction_check.json", "noise_ceiling.json", "build_sites_analysis.json"):
    obj, _ = _read_result(cfg, name)
    print(f"{name:28s} current under 22dec94 code: {result_staleness(cfg, obj) is None} ({result_staleness(cfg, obj)})")
rc, _ = _read_result(cfg, "reproduction_check.json")
print("committed table summary:", rc["summary"])
order = [s.name for s in _stages()]
for s in _stages():
    if order.index(s.name) > order.index(GATE):
        print(f"  gate for {s.name:24s} needs={'/'.join(s.needs):30s} -> {_gate_status(cfg, {}, [], s.needs)}")
nc, _ = _read_result(cfg, "noise_ceiling.json")
print("noise_ceiling.json top-level keys:", sorted(k for k in nc if not k.startswith("_"))[:20])
print("noise_ceiling.json _inputs:", sorted(nc.get("_inputs", {})))
readme = (ROOT / "README.md").read_text().splitlines()
print("README (22dec94) lines 25-27:", " ".join(x.strip() for x in readme[24:27]))
cur = Path("/home/user/MSHI/README.md").read_text().splitlines()
print("README (HEAD)   lines 25-27:", " ".join(x.strip() for x in cur[24:27]))
print("README (HEAD)   lines 59-61:", " ".join(x.strip() for x in cur[58:61]))
log = [json.loads(x) for x in (ROOT / "results" / "run_log.jsonl").read_text().splitlines()]
for r in log[-25:]:
    if r["stage"] in ("repro_checks", "noise_ceiling"):
        print(f"  run log: {r['start_utc']} {r['stage']:14s} {r['status'][:40]:40s} commit {r['git_commit']} invocation {r['invocation']}")
