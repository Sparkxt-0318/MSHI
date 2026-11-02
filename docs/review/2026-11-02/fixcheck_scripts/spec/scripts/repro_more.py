import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.io import write_result
from mshi.analysis import repro_checks as RC
S = Path(sys.argv[1]); shutil.rmtree(S, ignore_errors=True)
base = load_config()
def mk(edit=None):
    d = copy.deepcopy(base.data); d["paths"]["raw"] = str(S / "raw")
    if edit: edit(d)
    return Config(d, source=base.source, out_root=S / "out")
c = mk()
for f in ["build_sites.json", "cosore_annual.json"]:
    o = json.loads(base.path("results", f).read_text()); o.pop("_provenance"); write_result(c, o, f)
qc = {"selected": {"set": "TP", "learner": "OLS-TP", "cv_r2": 0.143}, "primary": {"n": 235, "r2": 0.079, "ci_site": [0.013, 0.125]},
      "vs_locked": {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}}
repo = {"selected": {"set": "C8", "learner": "XGB", "cv_r2": 0.2}, "primary": {"n": 290, "r2": -0.3, "ci_site": [-0.5, -0.1]},
        "vs_locked": {"identical": False, "selected_same": False, "max_abs_primary_diff": 0.4}}
write_result(c, qc, "clean_test_rerun_qc.json"); write_result(c, repo, "clean_test_rerun_repo.json")
s = RC.repro_checks(c)
rows = json.loads(c.path("results", "reproduction_check.json").read_text())["rows"]
print("repo variant deviates (selected XGB, max diff 0.4); summary:", s)
print("rows mentioning repo variant:", [r["quantity"] for r in rows if "repo" in r["quantity"].lower() and "Repo-filter sites" not in r["quantity"]])
# stale locked rows: rerun written under another config
c2 = mk(lambda d: d["smoke"].__setitem__("seed", 7))
for f in ["build_sites.json", "cosore_annual.json"]:
    o = json.loads(base.path("results", f).read_text()); o.pop("_provenance"); write_result(c2, o, f)
s2 = RC.repro_checks(c2)
rows = json.loads(c2.path("results", "reproduction_check.json").read_text())["rows"]
print("stale rerun: summary", s2, [(r["quantity"][:30], r["status"]) for r in rows if r["quantity"].startswith("Locked")][:3])
