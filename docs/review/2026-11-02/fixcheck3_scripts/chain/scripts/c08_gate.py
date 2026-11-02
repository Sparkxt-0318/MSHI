"""Re-check spec-new-06 (the reproduction gate) with the real stages plus later-phase stand-ins appended."""
import sys, json, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc
logging.basicConfig(level=logging.ERROR)
cc.stub_git()
import mshi.run as R
ran = []
def mk(n):
    def f(c):
        ran.append(n); return {"ok": n}
    return f
real = R._stages
R._stages = lambda: real() + [R.Stage("phase2_nodep", mk("phase2_nodep"), []),
                              R.Stage("phase2_sites", mk("phase2_sites"), ["build_sites"]),
                              R.Stage("phase2_gated", mk("phase2_gated"), ["repro_checks"])]
P2 = ["phase2_nodep", "phase2_sites", "phase2_gated"]
base = cc.SCR / "work" / "c08"
cc.reset(base)
fail = lambda d: d["reproduction_targets"]["srdb_repo_filter_records"].__setitem__("value", 4770)
s = cc.full_sand("s", fail, base=base)
cc.link_raw(s)
cc.seed_committed(s)
code = R.run(["build_sites", "repro_checks"] + P2, s)
print("(1) FAIL in the same invocation: exit", code, {k: v[:90] for k, v in cc.statuses(s).items()}, "ran:", ran)
n = len(cc.runlog(s)); ran.clear()
code = R.run(P2, s)
print("(2) later stages alone, stored FAIL: exit", code, {k: v[:110] for k, v in cc.statuses(s, n).items()}, "ran:", ran)
ok = cc.full_sand("s", base=base)                     # target restored: the stored table is now from another config
n = len(cc.runlog(ok)); ran.clear()
code = R.run(P2, ok)
print("(3) stored table from another config: exit", code, {k: v[:120] for k, v in cc.statuses(ok, n).items()}, "ran:", ran)
cc.seed_committed(ok)
n = len(cc.runlog(ok)); ran.clear()
code = R.run(["repro_checks"] + P2, ok)
print("(4) PASS in the same invocation: exit", code, cc.statuses(ok, n), "ran:", ran)
n = len(cc.runlog(ok)); ran.clear()
code = R.run(P2, ok)
print("(5) stored PASS table: exit", code, cc.statuses(ok, n), "ran:", ran)
ok.path("results", "reproduction_check.md").write_text("edited\n")
n = len(cc.runlog(ok)); ran.clear()
code = R.run(P2, ok)
print("(6) stored table, md edited: exit", code, {k: v[:120] for k, v in cc.statuses(ok, n).items()}, "ran:", ran)
# smoke runs: repro_checks is never run, so stages after it can never run (also with --stage all)
sm = cc.smoke_sand("c08/smoke")
R._stages = lambda: [R.Stage("build_sites", mk("build_sites"), []), R.Stage("repro_checks", mk("repro_checks"), []),
                     R.Stage("phase2_nodep", mk("phase2_nodep"), [])]
ran.clear()
code = R.run(["build_sites", "repro_checks", "phase2_nodep"], sm, full=True)
print("(7) smoke --stage all: exit", code, cc.statuses(sm), "ran:", ran)
n = len(cc.runlog(sm)); ran.clear()
code = R.run(["phase2_nodep"], sm)
print("(8) smoke, later stage alone: exit", code, cc.statuses(sm, n), "ran:", ran)
