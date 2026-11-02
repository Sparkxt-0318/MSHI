"""Claim 3 (rgd-deviation-atol-unanchored): is clean_test.deviation_atol pinned by anything?

Read-only on the repo. All outputs go to the sandbox under SCR/work/atol_*.
1. 9e17a36: the AST pin of clean_test.py+spatial.py; does changing the 1e-9 default change it?
2. HEAD: with deviation_atol edited to 0.05 in an in-memory config (sandbox out_root), do verify_lock,
   the BRIEF_TARGETS test, the anchor test, and the regression tests on a synthetic re-run pass, and does the
   re-run row flip DEVIATION -> PASS? Nothing is scored: the re-run is a copy of the locked JSON with
   primary.r2 + 0.004.
"""
import ast
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/user/MSHI")
SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import pytest  # noqa: E402

from mshi.config import Config, load_config  # noqa: E402
from mshi.analysis import clean_test as CT  # noqa: E402
from mshi.analysis.repro_checks import repro_checks  # noqa: E402
from mshi.io import write_result  # noqa: E402
import test_guards as TG  # noqa: E402
import test_regression as TR  # noqa: E402


def git_show(rev, path):
    return subprocess.run(["git", "--no-optional-locks", "-C", str(REPO), "show", f"{rev}:{path}"],
                          capture_output=True, text=True, check=True).stdout


def ast_digest_texts(texts):
    h = hashlib.sha256()
    for t in texts:
        tree = TG._strip_docstrings(ast.parse(t))
        h.update(ast.dump(tree, annotate_fields=True, include_attributes=False).encode())
    return h.hexdigest()


print("== 1. old pin at 9e17a36 ==")
ct_old = git_show("9e17a36", "mshi/analysis/clean_test.py")
sp_old = git_show("9e17a36", "mshi/spatial.py")
tg_old = git_show("9e17a36", "tests/test_guards.py")
pin_old = [l for l in tg_old.splitlines() if l.startswith("LOCKED_CODE_AST_SHA256")][0]
print("pin in 9e17a36 tests/test_guards.py:", pin_old)
print("digest of 9e17a36 clean_test.py+spatial.py:", ast_digest_texts([ct_old, sp_old]))
assert ct_old.count("atol: float = 1e-9") == 1
ct_old_edit = ct_old.replace("atol: float = 1e-9", "atol: float = 0.05")
print("digest with the default edited to 0.05:", ast_digest_texts([ct_old_edit, sp_old]))
print("HEAD digest (pin LOCKED_CODE_AST_SHA256 = %s):" % TG.LOCKED_CODE_AST_SHA256,
      ast_digest_texts([(REPO / "mshi/analysis/clean_test.py").read_text(), (REPO / "mshi/spatial.py").read_text()]))

print("\n== 2. HEAD: config edit deviation_atol 1e-9 -> 0.05 ==")
cfg = load_config()
locked = json.loads(cfg.repo_path(cfg["clean_test"]["locked_results"]["qc"]["file"]).read_text())
R = copy.deepcopy(locked)
R["primary"]["r2"] = locked["primary"]["r2"] + 0.004          # inside the +-0.01 target; a deviation from the locked result
R.pop("_provenance", None)

for atol in (1.0e-9, 0.05):
    data = copy.deepcopy(cfg.data)
    data["clean_test"]["deviation_atol"] = atol
    root = SCR / "work" / f"atol_{atol:g}"
    shutil.rmtree(root, ignore_errors=True)
    sand = Config(data, source=cfg.source, out_root=root)
    print(f"\n-- deviation_atol = {atol:g}; config sha {sand.sha256()[:12]} (repo config {cfg.sha256()[:12]})")
    print("verify_lock:", "ok" if CT.verify_lock(sand) else "?")
    for name in ["test_reproduction_targets_are_the_briefs", "test_lock_ok_on_repo",
                 "test_config_hashes_equal_code_anchors"]:
        getattr(TG, name)(sand)
        print(name, "PASSED")
    rr = copy.deepcopy(R)
    rr["vs_locked"] = CT.compare_with_locked(rr, locked, sand["clean_test"]["deviation_atol"])
    rr["lock"] = CT.verify_lock(sand)
    rr["variant"] = "qc"
    write_result(sand, rr, "clean_test_rerun_qc.json")
    print("vs_locked:", {k: rr["vs_locked"][k] for k in ("identical", "selected_same", "max_abs_primary_diff")})
    summary = repro_checks(sand)
    print("repro summary:", summary)
    rows = json.loads(sand.path("results", "reproduction_check.json").read_text())["rows"]
    row = [r for r in rows if r["quantity"] == "Locked test: re-run identical to the locked result"][0]
    print("re-run row:", {k: row[k] for k in ("v3", "tolerance", "status", "note")})
    eu = [r for r in rows if r["quantity"] == "Locked test: Europe R²"][0]
    print("Europe R2 row:", {k: eu[k] for k in ("handoff", "v3", "tolerance", "status")})
    md = sand.path("results", "reproduction_check.md").read_text()
    print("md line:", [l for l in md.splitlines() if "re-run identical" in l and "repo-filter" not in l][0])
    for name, args in [("test_locked_test_rerun", ()), ("test_locked_rerun_reported_against_locked_result", ("qc",)),
                       ("test_reproduction_table_has_no_fail", ())]:
        try:
            getattr(TR, name)(sand, *args)
            print(name, "PASSED")
        except pytest.skip.Exception as e:
            print(name, "SKIPPED", e)
        except AssertionError as e:
            print(name, "FAILED", e)
