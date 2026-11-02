"""Claim 1: a future fresh clone (results of a networked run committed, gitignored interim/raw absent).
Does `make repro` / `make data` exit 2 with STALE NPP rows, and does `make test` then fail?"""
import json
import logging
import shutil
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.WARNING)
from mshi.run import _gate_status, run  # noqa: E402

base = vc.reset(vc.WORK / "v1")
sand = vc.full_sand(base / "s")

# ---- the author's state after a networked `make all` (synthetic rasters / MODIS values; nothing scored)
vc.seed_committed(sand)
vc.synthetic_rasters(sand)
vc.write_modis_stage(sand, vc.synthetic_modis_table(sand, noise_frac=0.19, seed=1))
print("features exit:", run(["features"], sand))
vc.locked_reruns(sand)
print("repro exit (author state):", run(["repro_checks"], sand))
t = vc.table(sand)
print("author summary:", t["summary"], "npp r:", t["npp_check"] and round(t["npp_check"]["pearson_r"], 4))
print("author staleness:", json.dumps(vc.staleness_all(sand), indent=1))
print("author regression:", json.dumps(vc.regression(sand), indent=1))
print("author gate:", _gate_status(sand, {}, ["later_stage"]))
outs = {k: sorted(json.loads(sand.path("results", k).read_text()).get("_outputs", {}))
        for k in ("modis_points.json", "features.json", "fetch_worldclim.json", "fetch_soilgrids.json")}
print("recorded output root keys:", {k: (v[:2] if len(v) > 2 else v) for k, v in outs.items()})

# ---- fresh clone: gitignored roots absent (data/raw/, data/interim/), committed results/ and data/derived/ present
for r in ("interim", "raw"):
    shutil.rmtree(sand.path(r))
print("\nfresh-clone staleness:", json.dumps({k: (v[:90] if v else v) for k, v in vc.staleness_all(sand).items()}, indent=1))
print("fresh-clone regression (committed table):", json.dumps(vc.regression(sand), indent=1))
print("fresh-clone gate (committed table):", _gate_status(sand, {}, ["later_stage"]))

# ---- `make repro`
n = len(vc.runlog(sand))
code = run(["repro_checks"], sand)
print("\nmake repro: exit", code, vc.statuses(sand, n))
t = vc.table(sand)
print("summary:", t["summary"], "npp_check:", t["npp_check"])
for r in t["rows"]:
    if r["status"] != "PASS":
        print("   ", r["status"], "|", r["quantity"][:60], "|", r["note"].replace(str(base), "<v1>")[:150])
print("after make repro regression:", json.dumps(vc.regression(sand), indent=1))
print("after make repro gate:", _gate_status(sand, {}, ["later_stage"]))

# ---- `make data` emulation (pinned raw inputs present again, as the fetch stages would leave them; COSORE annual
# is the committed, current table; git is never run in data/raw)
vc.link_raw(sand)
vc.stub_git()
n = len(vc.runlog(sand))
code = run(["fetch_srdb", "fetch_naturalearth", "build_sites", "repro_checks"], sand)
print("\nmake data (emulated, without fetch_cosore/cosore_annual): exit", code, vc.statuses(sand, n))
t = vc.table(sand)
print("summary:", t["summary"])
print("regression:", json.dumps(vc.regression(sand), indent=1))
