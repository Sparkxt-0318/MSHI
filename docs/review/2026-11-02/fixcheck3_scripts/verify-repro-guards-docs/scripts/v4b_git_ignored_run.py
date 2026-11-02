"""Claim 4, end to end: mshi.run.run on fetch_cosore + cosore_annual in a full (non-smoke) sandbox whose COSORE
source is the local origin built by v4_git_ignored.py. Control: clean checkout. Case: a .DS_Store at the top of
the checkout. Prints statuses and exit codes. Writes only under S/work/git_run/. Run with python -I -B."""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")

from mshi.config import Config, load_config  # noqa: E402
from mshi.run import run  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
G = SCR / "work" / "git_ignored"
origin = G / "origin.git"
commit = subprocess.run(["git", "--git-dir", str(origin), "rev-parse", "HEAD"], capture_output=True, text=True,
                        check=True).stdout.strip()
W = SCR / "work" / "git_run"
shutil.rmtree(W, ignore_errors=True)
cfg = load_config()
data = copy.deepcopy(cfg.data)
for root in ("raw", "interim", "derived", "results", "figures"):
    data["paths"][root] = str(W / root)
data["sources"]["cosore"]["repo_url"] = f"file://{origin}"
data["sources"]["cosore"]["commit"] = commit
sand = Config(data, source=cfg.source)
print("sandbox out_root:", sand.out_root, "| raw:", sand.path("raw"))

code = run(["fetch_cosore", "cosore_annual"], sand)
log = [json.loads(l) for l in sand.path("results", "run_log.jsonl").read_text().splitlines()]
print("control (clean checkout): exit", code, [(r["stage"], r["status"][:60]) for r in log])

from mshi.data.fetch import cosore_repo_path  # noqa: E402
(cosore_repo_path(sand) / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
code = run(["fetch_cosore", "cosore_annual"], sand)
log = [json.loads(l) for l in sand.path("results", "run_log.jsonl").read_text().splitlines()][2:]
print("with .DS_Store:           exit", code, [(r["stage"], r["status"][:110]) for r in log])
code = run(["cosore_annual"], sand)
log = [json.loads(l) for l in sand.path("results", "run_log.jsonl").read_text().splitlines()][4:]
print("cosore_annual alone:      exit", code, [(r["stage"], r["status"][:110]) for r in log])
