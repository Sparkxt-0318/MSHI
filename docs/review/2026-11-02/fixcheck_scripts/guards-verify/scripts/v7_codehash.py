"""Claim 7: write_result stamps the code hash of the files on disk at WRITE time, not of the code that ran.

Uses a scratch COPY of mshi/ + configs/ (imported from the copy, so the real package is never edited).
A fake stage (registered through mshi.run._stages) simulates another session editing the package while the
stage runs, then writes its result with write_result.
"""
import json
import os
import shutil
import sys

SCR = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards-verify"
sys.dont_write_bytecode = True
os.environ["GIT_OPTIONAL_LOCKS"] = "0"
COPY = os.path.join(SCR, "work", "v7", "pkgcopy")
shutil.rmtree(os.path.dirname(COPY), ignore_errors=True)
os.makedirs(COPY)
shutil.copytree("/home/user/MSHI/mshi", os.path.join(COPY, "mshi"), ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree("/home/user/MSHI/configs", os.path.join(COPY, "configs"))
sys.path.insert(0, COPY)

import copy  # noqa: E402
from pathlib import Path  # noqa: E402

import mshi  # noqa: E402

assert Path(mshi.__file__).resolve().is_relative_to(Path(COPY)), mshi.__file__
import mshi.run as R  # noqa: E402
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import read_json, result_staleness, write_result  # noqa: E402
from mshi.runlog import code_sha256  # noqa: E402

base = load_config()
data = copy.deepcopy(base.data)
work = Path(COPY).parent / "out"
for k in ("interim", "derived", "results", "figures", "raw"):
    data["paths"][k] = str(work / k)
cfg = Config(data, source=base.source, out_root=None)
target = Path(COPY) / "mshi" / "analysis" / "repro_checks.py"


def stage(c):
    ran_with = code_sha256()                         # hash of the code this stage is executing
    # another session edits the package while this stage is still running
    target.write_text(target.read_text().replace('"""Compare pipeline outputs', '"""EDITED. Compare pipeline outputs', 1))
    write_result(c, {"value": 1}, "fake_stage.json")
    return {"ran_with": ran_with}


R._stages = lambda: [R.Stage("fake_stage", stage, [], "")]
start_hash = code_sha256()
code = R.run(["fake_stage"], cfg)
rec = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-1]
res = read_json(cfg.path("results", "fake_stage.json"))
print("exit", code)
print("code hash at start of run      ", start_hash[:12])
print("run_log record code_sha256     ", rec["code_sha256"][:12])
print("result _provenance.code_sha256 ", res["_provenance"]["code_sha256"][:12])
print("code hash on disk now          ", code_sha256()[:12])
print("result_staleness(result)       ", result_staleness(cfg, res))
print("anything compares run_log vs result hash? (grep below)")
