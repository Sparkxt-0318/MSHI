"""Claim 7: can a config-only edit of reproduction_targets undo the Europe-n exactness (spec-05) or loosen a
target so that both the reproduction table and the regression tests pass?

Usage: python -B c7_targets.py <sandbox_dir>
No locked test is run: the re-run JSON is the locked result with primary.n changed (synthetic).
"""
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import write_result  # noqa: E402
from mshi.analysis import repro_checks as RC  # noqa: E402
from mshi.analysis.clean_test import compare_with_locked  # noqa: E402
import test_regression as TR  # noqa: E402

ROOT = Path(sys.argv[1])
shutil.rmtree(ROOT, ignore_errors=True)
base = load_config()
locked = json.loads(base.path("handoff", "results", "clean_test_europe.json").read_text())


def mk(name, edit=None):
    d = copy.deepcopy(base.data)
    d["paths"]["raw"] = str(ROOT / name / "raw")
    if edit:
        edit(d)
    return Config(d, source=base.source, out_root=ROOT / name / "out")


def setup(c):
    for f in ["build_sites.json", "cosore_annual.json"]:
        o = json.loads(base.path("results", f).read_text())
        o.pop("_provenance")
        write_result(c, o, f)
    R = copy.deepcopy(locked)
    R["primary"]["n"] = 236                         # the closed Europe test set changed by one site
    R["vs_locked"] = compare_with_locked(R, locked)
    R["lock"] = {"locked_sha256": c["clean_test"]["locked_sha256"]}
    write_result(c, R, "clean_test_rerun_qc.json")


for name, edit in [("exact (as committed)", None),
                   ("europe_n loosened to rel 0.02", lambda d: d["reproduction_targets"]["locked_test"].__setitem__(
                       "europe_n", {"value": 235, "rel": 0.02}))]:
    c = mk(name.split()[0], edit)
    setup(c)
    try:
        s = RC.repro_checks(c)
        outcome = f"summary {s}"
    except RC.ReproductionFailure as e:
        outcome = f"ReproductionFailure: {str(e)[:80]}"
    rows = json.loads(c.path("results", "reproduction_check.json").read_text())["rows"]
    print(f"[{name}] {outcome}")
    for r in rows:
        if r["quantity"] in ("Locked test: Europe n", "Locked test: re-run identical to the locked result"):
            print(f"[{name}]   {r['quantity']}: {r['status']} (v3={r['v3']}, tolerance={r['tolerance']})")
    tests = {}
    for t in ("test_locked_test_rerun", "test_locked_rerun_reported_against_locked_result",
              "test_reproduction_table_has_no_fail"):
        try:
            getattr(TR, t)(c)
            tests[t] = "passed"
        except BaseException as e:  # noqa: BLE001
            tests[t] = f"{type(e).__name__}: {str(e)[:60]}"
    print(f"[{name}]   tests: {tests}")

# NPP target: loosening the tolerance in the config alone turns a FAIL into a PASS
for t in ({"value": 0.982, "abs": 0.01}, {"value": 0.982, "abs": 0.05}):
    print("NPP r = 0.95 with target", t, "->", RC._row("NPP r", t, 0.95)["status"])
