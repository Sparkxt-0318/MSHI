"""Claim 6: in a smoke run (out_root set) repro_checks is skipped without a status, so a stage ordered after it
is always skipped ('gate closed (repro_checks: not run)') and the run exits 2; alone, it looks for a sandbox
table that smoke runs never write. Stand-in stages only (build_sites, repro_checks, later_stage)."""
import json
import logging
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
import mshi.run as R  # noqa: E402

called = []


def mk(name):
    def f(cfg):
        called.append(name)
        return {"ok": name}
    return f


R._stages = lambda: [R.Stage("build_sites", mk("build_sites")), R.Stage("repro_checks", mk("repro_checks")),
                     R.Stage("later_stage", mk("later_stage"), ["build_sites"])]
names = ["build_sites", "repro_checks", "later_stage"]
for label, cfg in (("smoke", vc.smoke_sand(vc.reset(vc.WORK / "v6" / "smoke"))),
                   ("non-smoke", vc.full_sand(vc.reset(vc.WORK / "v6" / "full")))):
    called.clear()
    code = R.run(names, cfg, full=True)
    print(f"[{label}] run(all) exit {code}; called {called}; statuses {json.dumps(vc.statuses(cfg))}")
    called.clear()
    n = len(vc.runlog(cfg))
    code = R.run(["later_stage"], cfg)
    print(f"[{label}] run([later_stage]) alone exit {code}; called {called}; statuses {json.dumps(vc.statuses(cfg, n))[:200]}")

# the real stage list today: is any stage ordered after repro_checks?
R2 = __import__("importlib").reload(R)
order = [s.name for s in R2._stages()]
print("real stages:", order, "| stages after repro_checks:", order[order.index("repro_checks") + 1:])
