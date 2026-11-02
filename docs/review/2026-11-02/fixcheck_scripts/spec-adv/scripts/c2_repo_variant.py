"""Claim 2: is a deviating repo-filter-sensitivity re-run surfaced by repro_checks?

Usage: python -B c2_repo_variant.py <sandbox_dir>
Writes only into the sandbox (out_root). Uses synthetic re-run JSONs (no real Europe outcome scored).
"""
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import write_result  # noqa: E402
from mshi.analysis import repro_checks as RC  # noqa: E402

S = Path(sys.argv[1])
shutil.rmtree(S, ignore_errors=True)
base = load_config()
d = copy.deepcopy(base.data)
d["paths"]["raw"] = str(S / "raw")
c = Config(d, source=base.source, out_root=S / "out")
for f in ["build_sites.json", "cosore_annual.json"]:
    o = json.loads(base.path("results", f).read_text())
    o.pop("_provenance")
    write_result(c, o, f)

locked_qc = json.loads(base.path("handoff", "results", "clean_test_europe.json").read_text())
locked_repo = json.loads(base.path("handoff", "results", "clean_test_europe_repo_sensitivity.json").read_text())
print("locked qc selected:", locked_qc["selected"]["set"], locked_qc["selected"]["learner"],
      "| locked repo selected:", locked_repo["selected"]["set"], locked_repo["selected"]["learner"],
      "n", locked_repo["primary"]["n"])

# qc re-run identical to the locked result (copy of the locked JSON + an identical vs_locked block)
qc = copy.deepcopy(locked_qc)
qc["vs_locked"] = {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}
# repo re-run deviating: other model, Europe numbers moved
repo = copy.deepcopy(locked_repo)
repo["selected"] = {**repo["selected"], "set": "C8", "learner": "XGB"}
repo["primary"] = {**repo["primary"], "r2": repo["primary"]["r2"] - 0.4}
repo["vs_locked"] = {"identical": False, "selected_same": False, "max_abs_primary_diff": 0.4}
write_result(c, qc, "clean_test_rerun_qc.json")
write_result(c, repo, "clean_test_rerun_repo.json")

s = RC.repro_checks(c)
rows = json.loads(c.path("results", "reproduction_check.json").read_text())["rows"]
print("summary:", s)
print("rows with status DEVIATION:", [r["quantity"] for r in rows if r["status"] == "DEVIATION"])
print("rows whose quantity/note mention 'repo':",
      [(r["quantity"], r["status"]) for r in rows if "repo" in (r["quantity"] + r.get("note", "")).lower()])
print("locked rows:", [(r["quantity"], r["status"]) for r in rows if r["quantity"].startswith("Locked")])
md = c.path("results", "reproduction_check.md").read_text()
print("'XGB' in reproduction_check.md:", "XGB" in md, "| 'sensitivity' in md:", "sensitivity" in md.lower())

# second case: qc re-run deviates -> is it reported?
qc2 = copy.deepcopy(qc)
qc2["vs_locked"] = {"identical": False, "selected_same": True, "max_abs_primary_diff": 0.02}
write_result(c, qc2, "clean_test_rerun_qc.json")
s2 = RC.repro_checks(c)
print("control (qc variant deviates):", s2)
