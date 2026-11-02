"""Claim 5 with a clean control: results re-stamped under the sandbox config (all PASS) vs an unrelated config edit
(all STALE). Same exit code? What does the console log say?"""
import io
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path, sandbox  # noqa: E402

buf = io.StringIO()
logging.basicConfig(level=logging.INFO, stream=buf, format="%(levelname)s %(name)s: %(message)s")
from mshi.io import read_json, write_result  # noqa: E402
from mshi.run import run  # noqa: E402

W = WORK / "v5b"; shutil.rmtree(W, ignore_errors=True)


def committed(name):
    d = json.loads((Path(REPO) / "results" / name).read_text())
    d.pop("_provenance", None)
    return d


for tag, edit in [("control (results stamped by this config)", None),
                  ("smoke.seed edited", lambda d: d["smoke"].__setitem__("seed", 1))]:
    base = sandbox(W / "ctl")                       # stamp with the unedited sandbox config
    if edit is None:
        shutil.rmtree(W / "ctl", ignore_errors=True)
        for f in ("build_sites.json", "cosore_annual.json"):
            write_result(base, committed(f), f)
    cfg = sandbox(W / "ctl", edit=edit)
    buf.truncate(0); buf.seek(0)
    code = run(["repro_checks"], cfg)
    s = read_json(cfg.path("results", "reproduction_check.json"))["summary"]
    lines = [x for x in buf.getvalue().splitlines() if "repro" in x or "stages not completed" in x]
    print(f"[{tag}] exit {code}; summary {s}; console: {lines}")
