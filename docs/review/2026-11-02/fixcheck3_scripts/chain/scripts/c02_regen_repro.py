"""Regenerate reproduction_check.json/.md from the committed results and the 15:15 invocation statuses (smoke-mode
sandbox with an identical config dict, so config hash is unchanged); compare bytes with the committed files."""
import sys, json, copy, shutil, hashlib
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.analysis.repro_checks import repro_checks
SCR = Path(sys.argv[1])
shutil.rmtree(SCR, ignore_errors=True)
cfg = load_config()
sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=SCR)
assert sand.sha256() == cfg.sha256()
sand.path("results").mkdir(parents=True)
sand.path("derived").mkdir(parents=True)
for p in cfg.path("results").glob("*.json"):
    if not p.name.startswith("reproduction_check"):
        shutil.copy(p, sand.path("results", p.name))
for p in cfg.path("derived").iterdir():
    shutil.copy(p, sand.path("derived", p.name))
recs = [json.loads(l) for l in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
last = [r for r in recs if r["start_utc"] >= "2026-11-02T15:15"]
status = {r["stage"]: r["status"] for r in last if r["stage"] != "repro_checks"}
print("statuses:", {k: v[:40] for k, v in status.items()})
sand.invocation = {"stages": [r["stage"] for r in last], "status": status}
print("summary:", repro_checks(sand))
for f in ["reproduction_check.json", "reproduction_check.md"]:
    a, b = sand.path("results", f).read_bytes(), cfg.path("results", f).read_bytes()
    print(f, "identical" if a == b else "DIFFERENT", hashlib.sha256(a).hexdigest()[:12], hashlib.sha256(b).hexdigest()[:12])
