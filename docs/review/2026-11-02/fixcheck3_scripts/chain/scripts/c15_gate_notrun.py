"""The gate counts NOT RUN rows as passing: build_sites fails in the invocation, its current stored outputs
come from a build that does not reproduce, and a later stage that does not list build_sites runs."""
import sys, os, shutil, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc
logging.basicConfig(level=logging.CRITICAL)
cc.stub_git()
import mshi.run as R
from mshi.io import require_outputs
from mshi.data.fetch import srdb_csv_path
ran = []
def phase2(c):
    require_outputs(c, "build_sites.json", [c.path("derived", f) for f in ("sites_v3_qc.parquet", "sites_v3_repo.parquet")])
    ran.append("phase2"); return {}
real = R._stages
R._stages = lambda: real() + [R.Stage("phase2_transfer", phase2, ["features"])]
base = cc.SCR / "work" / "c15"; cc.reset(base)
B = lambda d: d["site_build"].__setitem__("merge_radius_km", 20.0)     # a build that does not reproduce
s = cc.full_sand("s", B, base=base)
cc.link_raw(s)
cc.seed_committed(s, names=("cosore_annual.json",))
print("build_sites under B:", R.run(["build_sites"], s), cc.statuses(s))
n = len(cc.runlog(s))
print("control repro_checks alone:", R.run(["repro_checks", "phase2_transfer"], s), {k: v[:100] for k, v in cc.statuses(s, n).items()}, cc.summary(s))
# SRDB input now fails its checksum (e.g. a truncated re-download); the stored B build stays current
p = srdb_csv_path(s); os.unlink(p); p.write_bytes(srdb_csv_path(cc.CFG).read_bytes()[:-10])
n = len(cc.runlog(s)); ran.clear()
code = R.run(["build_sites", "repro_checks", "phase2_transfer"], s)
print("build_sites error + repro + later stage: exit", code, {k: v[:100] for k, v in cc.statuses(s, n).items()}, cc.summary(s), "ran:", ran)
n = len(cc.runlog(s)); ran.clear()
code = R.run(["phase2_transfer"], s)
print("later stage alone afterwards (stored table): exit", code, cc.statuses(s, n), "gate:", R._gate_status(s, {}, ["phase2_transfer"]), "ran:", ran)
from mshi.io import result_staleness, read_json
print("build_sites.json (config B build) staleness:", result_staleness(s, read_json(s.path("results", "build_sites.json"))))
