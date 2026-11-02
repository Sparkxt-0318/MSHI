"""The stored reproduction table (gate, regression tests) is not bound to the results it summarised.
Author state (table PASS, gate open) -> gitignored roots lost (fresh clone / cache cleaned) -> `make features`
re-extracts MODIS (live catalog stands in: extract_points patched to return other values, same config/code)
-> a later-phase stage run alone passes the gate on the author's table; `make test` passes; a fresh
repro_checks gives FAIL."""
import sys, json, shutil, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
sys.path.insert(0, "/home/user/MSHI/tests")
import numpy as np
import cc, author
logging.basicConfig(level=logging.WARNING)
import mshi.run as R
import mshi.data.modis as M
import mshi.netutil as N
from mshi.io import require_outputs, result_staleness, read_json
base = cc.SCR / "work" / "c10"
cc.reset(base)
sand, cf, cr = author.build("s", base)
print("author state: features exit", cf, "repro exit", cr, "summary", cc.summary(sand))
author_md = sand.path("results", "reproduction_check.md").read_bytes()
from mshi.io import sha256_file
feat_before = sha256_file(sand.path("interim", "features_v3_qc.parquet"))

ran = []
def phase2(c):
    require_outputs(c, "features.json", [c.path("interim", f"features_v3_{t}.parquet") for t in ("qc", "repo")])
    ran.append("phase2")
    return {"ok": True}
real = R._stages
R._stages = lambda: real() + [R.Stage("phase2_transfer", phase2, ["features"], "later phase (stand-in)")]

# --- gitignored roots lost; `make features` re-extracts (other values), same config and code
for r in ("interim", "raw"):
    shutil.rmtree(sand.path(r))
author.fake_fetch_rasters(sand)                      # stands in for the re-download (identical rasters)
changed = author.fake_modis_values(sand, noise=1.5, seed=7)   # the live catalog now gives other NPP values
N.check_reachable = lambda *a, **k: None
M.extract_points = lambda pts, m, **k: (changed.set_index("site_key").loc[pts.site_key].reset_index(),
                                        {"failed_reads": [], "catalog_gaps": [], "n_tiles": 1, "n_jobs": 1,
                                         "accepted_catalog_gaps": [], "lst_same_date_ties": [],
                                         "npp_duplicate_years": []})
n = len(cc.runlog(sand))
code = R.run(["modis_points", "features"], sand)
print("make features (re-extraction):", code, cc.statuses(sand, n))
for p in sorted(sand.path("results").glob("*.json")):
    print(f"   {p.name:28s} {result_staleness(sand, read_json(p))}")
print("features_v3_qc.parquet changed:", feat_before != sha256_file(sand.path("interim", "features_v3_qc.parquet")),
      "| clean_test_rerun_qc.json staleness:", result_staleness(sand, read_json(sand.path("results", "clean_test_rerun_qc.json"))))
print("stored table unchanged:", sand.path("results", "reproduction_check.md").read_bytes() == author_md)
print("gate:", R._gate_status(sand, {}, ["phase2_transfer"]))
n = len(cc.runlog(sand))
code = R.run(["phase2_transfer"], sand)
print("later-phase stage alone:", code, cc.statuses(sand, n), "ran:", ran)
import test_regression as TR
out = {}
for t in ["test_npp_correlation", "test_reproduction_table_has_no_fail", "test_locked_test_rerun"]:
    try:
        getattr(TR, t)(sand); out[t] = "pass"
    except BaseException as e:
        out[t] = f"{type(e).__name__}: {str(e)[:100]}"
print("regression tests:", out)
print("stored npp_check r:", read_json(sand.path("results", "reproduction_check.json"))["npp_check"]["pearson_r"])
n = len(cc.runlog(sand))
code = R.run(["repro_checks", "phase2_transfer"], sand)
print("control, repro_checks now:", code, cc.statuses(sand, n))
print("NPP row now:", [(r["v3"], r["status"]) for r in cc.rows(sand) if r["quantity"].startswith("NPP")])
print("locked-test rows now:", [(r["quantity"][:45], r["status"]) for r in cc.rows(sand) if r["quantity"].startswith("Locked")][:3])
