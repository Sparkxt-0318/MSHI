"""Claim 1, refutation attempt: after `make data` left STALE NPP rows in a fresh clone, can `make all` in a
container where WorldClim, SoilGrids and Planetary Computer are blocked clear the state ("can never be cleared")?
Starts from the final state of v1_fresh_clone.py (sandbox work/v1/s)."""
import json
import logging
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.ERROR)
import mshi.data.fetch as FE  # noqa: E402
import mshi.data.modis as MO  # noqa: E402
import mshi.data.rasters as RA  # noqa: E402
import mshi.run as R  # noqa: E402
from mshi.netutil import SourceUnavailableError  # noqa: E402

sand = vc.full_sand(vc.WORK / "v1" / "s")
assert vc.table(sand)["summary"]["STALE"] == 2, "run v1_fresh_clone.py first"
vc.link_raw(sand)
vc.stub_git()


def blocked(host):
    def f(cfg):
        raise SourceUnavailableError(f"https://{host}/: blocked by proxy (Tunnel connection failed: 403)", kind="proxy_denied")
    return f


# the three gridded sources are blocked (as in this container); COSORE stages are stand-ins (seeded, current)
orig = R._stages


def stages():
    out = []
    for s in orig():
        if s.name == "fetch_worldclim":
            s.func = blocked("geodata.ucdavis.edu")
        elif s.name == "fetch_soilgrids":
            s.func = blocked("maps.isric.org")
        elif s.name == "modis_points":
            s.func = blocked("planetarycomputer.microsoft.com")
        elif s.name in ("fetch_cosore", "cosore_annual"):
            s.func = (lambda c, n=s.name: {"stand_in": n})
        out.append(s)
    return out


R._stages = stages
n = len(vc.runlog(sand))
names = [s.name for s in stages()]
code = R.run(names, sand, full=True)
print("make all (blocked container) exit:", code)
print("statuses:", json.dumps(vc.statuses(sand, n), indent=1)[:2500])
t = vc.table(sand)
print("summary:", t["summary"])
for r in t["rows"]:
    if r["status"] != "PASS":
        print("   ", r["status"], "|", r["quantity"][:60], "|", r["note"][:110])
print("regression:", json.dumps(vc.regression(sand), indent=1))
from mshi.run import _gate_status  # noqa: E402
print("gate:", _gate_status(sand, {}, ["later_stage"]))
