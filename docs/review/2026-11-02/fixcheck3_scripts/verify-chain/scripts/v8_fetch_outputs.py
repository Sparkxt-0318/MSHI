"""Claim 8: fetch_srdb / fetch_naturalearth results record no _outputs, and build_sites reads the SRDB CSV and
Natural Earth file whether or not fetch_srdb.json / fetch_naturalearth.json exist or are current (it checks
the pinned SHA-256s instead). Pinned files are present (symlinks), so download() makes no request."""
import json
import logging
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
import mshi.run as R  # noqa: E402
from mshi.io import read_json, result_staleness, write_result  # noqa: E402

s = vc.full_sand(vc.reset(vc.WORK / "v8" / "s"))
vc.link_raw(s)
vc.seed_committed(s, names=("cosore_annual.json",))
n = len(vc.runlog(s))
print("run([fetch_srdb, fetch_naturalearth]) exit", R.run(["fetch_srdb", "fetch_naturalearth"], s), vc.statuses(s, n))
for f in ("fetch_srdb.json", "fetch_naturalearth.json"):
    d = read_json(s.path("results", f))
    print(f"   {f}: keys {sorted(d)} | _outputs: {d.get('_outputs')}")
print("committed results without _outputs:",
      sorted(p.name for p in (vc.REPO / "results").glob("*.json") if "_outputs" not in json.loads(p.read_text())))
# fetch results absent, then from another config: build_sites still runs on the pinned files
for f in ("fetch_srdb.json", "fetch_naturalearth.json"):
    s.path("results", f).unlink()
n = len(vc.runlog(s))
print("fetch results absent: run([build_sites]) exit", R.run(["build_sites"], s), vc.statuses(s, n))
other = vc.full_sand(vc.WORK / "v8" / "s", lambda d: d["smoke"].__setitem__("seed", 1))
write_result(other, {"other": True}, "fetch_srdb.json")
print("fetch_srdb.json now:", result_staleness(s, read_json(s.path("results", "fetch_srdb.json"))))
n = len(vc.runlog(s))
print("stale fetch_srdb.json: run([build_sites]) exit", R.run(["build_sites"], s), vc.statuses(s, n))
