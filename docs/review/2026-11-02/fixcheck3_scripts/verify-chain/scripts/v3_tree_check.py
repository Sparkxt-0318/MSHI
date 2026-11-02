"""Claim 3: import mshi from an exported tree (argv[1]) and report the code hash, the staleness of every committed
result, the lock anchors and verify_lock. Run once per tree (LF and CRLF exports of HEAD)."""
import json
import sys
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree))
sys.dont_write_bytecode = True
import mshi  # noqa: E402

assert Path(mshi.__file__).resolve().is_relative_to(tree), mshi.__file__
from mshi.analysis.clean_test import LOCKED_RESULT_SHA256, PLAN_SHA256, LockedPlanError, verify_lock  # noqa: E402
from mshi.config import load_config  # noqa: E402
from mshi.io import read_json, result_staleness, sha256_file  # noqa: E402
from mshi.runlog import code_sha256  # noqa: E402

cfg = load_config()
print("tree:", tree.name, "| mshi from:", Path(mshi.__file__).parent.relative_to(tree.parent))
print("code_sha256:", code_sha256()[:12], "| config_sha256:", cfg.sha256()[:12])
for p in sorted(cfg.path("results").glob("*.json")):
    if p.name == "environment.json":
        continue
    print(f"   {p.name:28s} {result_staleness(cfg, read_json(p))}")
plan = cfg.repo_path(cfg["clean_test"]["plan"])
print("plan sha == anchor:", sha256_file(plan) == PLAN_SHA256)
for t, d in LOCKED_RESULT_SHA256.items():
    print(f"locked result {t} sha == anchor:", sha256_file(cfg.repo_path(cfg["clean_test"]["locked_results"][t]["file"])) == d)
try:
    verify_lock(cfg)
    print("verify_lock: ok")
except LockedPlanError as e:
    print("verify_lock: LockedPlanError:", str(e)[:160].replace(str(tree), "<tree>"))
