"""Future fresh clone: the author's Phase-1-complete results are committed, but data/interim and data/raw
(gitignored) are absent. What do `make repro` / `make data` (repro_checks) and the regression tests show?"""
import sys, json, shutil, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
sys.path.insert(0, "/home/user/MSHI/tests")
import cc, author
logging.basicConfig(level=logging.WARNING)
from mshi.run import run, _gate_status
from mshi.io import result_staleness, read_json
base = cc.SCR / "work" / "c09"
cc.reset(base)
sand, cf, cr = author.build("s", base)
print("author state: features exit", cf, "repro exit", cr, "summary", cc.summary(sand))
print("author NPP row:", [(r["quantity"][:30], r["v3"], r["status"]) for r in cc.rows(sand) if r["quantity"].startswith(("NPP", "Original"))])
print("author gate for a later-phase stage:", _gate_status(sand, {}, ["phase2"]))
# --- fresh clone: gitignored roots absent
for r in ("interim", "raw"):
    shutil.rmtree(sand.path(r))
print("fresh clone staleness:")
for p in sorted(sand.path("results").glob("*.json")):
    print(f"   {p.name:28s} {result_staleness(sand, read_json(p))}")
# regression tests against the committed table (before anything is re-run)
import test_regression as TR
def emu(tag):
    out = {}
    for t in ["test_cosore_sites", "test_record_and_site_counts", "test_locked_test_rerun", "test_npp_correlation",
              "test_reproduction_table_has_no_fail"]:
        try:
            getattr(TR, t)(sand); out[t] = "pass"
        except BaseException as e:   # pytest.fail/skip raise BaseException subclasses
            out[t] = f"{type(e).__name__}: {str(e)[:120]}"
    for v in ("qc", "repo"):
        try:
            TR.test_locked_rerun_reported_against_locked_result(sand, v); out[f"rerun_{v}"] = "pass"
        except BaseException as e:
            out[f"rerun_{v}"] = f"{type(e).__name__}: {str(e)[:120]}"
    print(f"regression tests ({tag}):", json.dumps(out, indent=1))
emu("fresh clone, committed table")
n = len(cc.runlog(sand))
code = run(["repro_checks"], sand)          # `make repro` (the last stage of `make data` as well)
print("make repro exit:", code, cc.statuses(sand, n))
print("summary:", cc.summary(sand))
print("NPP rows:", [(r["quantity"][:40], r["status"], r["note"][:120]) for r in cc.rows(sand) if r["status"] != "PASS"])
emu("after make repro")
print("gate for a later-phase stage:", _gate_status(sand, {}, ["phase2"]))
