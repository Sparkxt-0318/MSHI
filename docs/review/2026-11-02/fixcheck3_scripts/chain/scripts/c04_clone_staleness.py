"""result_staleness of every committed result, with mshi imported from a clone (REPO_ROOT = the clone)."""
import sys, json
clone = sys.argv[1]
sys.path.insert(0, clone)
import mshi, hashlib
from pathlib import Path
assert Path(mshi.__file__).resolve().is_relative_to(Path(clone).resolve()), mshi.__file__
from mshi.config import load_config
from mshi.runlog import code_sha256
from mshi.io import result_staleness, sha256_file
from mshi.analysis import clean_test as CT
cfg = load_config()
print("clone", clone, "config", cfg.sha256()[:12], "code", code_sha256()[:12])
for p in sorted(cfg.path("results").glob("*.json")):
    if p.name == "environment.json":
        continue
    print(f"   {p.name:26s} {result_staleness(cfg, json.loads(p.read_text()))}")
plan = cfg.path("handoff", "ANALYSIS_PLAN_LOCKED.md")
print("plan sha256 == PLAN_SHA256:", sha256_file(plan) == CT.PLAN_SHA256)
for t, f in cfg["clean_test"]["locked_results"].items():
    print(f"locked result {t} sha256 == anchor:", sha256_file(cfg.repo_path(f["file"])) == CT.LOCKED_RESULT_SHA256[t])
try:
    CT.verify_lock(cfg); print("verify_lock: ok")
except Exception as e:
    print("verify_lock:", type(e).__name__, str(e)[:160])
