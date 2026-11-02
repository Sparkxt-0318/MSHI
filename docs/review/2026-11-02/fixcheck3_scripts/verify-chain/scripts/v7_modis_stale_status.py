"""Claim 7: a MODIS table refused by load_modis_points (StaleModisError / FileNotFoundError) while
modis_points.json is current. What status/exit code does `--stage features` give, and repro_checks on the same
state? (No network: check_reachable is replaced by a policy block, as in this container.)"""
import logging
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
import mshi.data.modis as M  # noqa: E402
import mshi.netutil as N  # noqa: E402
import mshi.run as R  # noqa: E402
from mshi.io import StaleInputError, read_json, result_staleness  # noqa: E402
from mshi.netutil import SourceUnavailableError  # noqa: E402


def blocked(url, **k):
    raise SourceUnavailableError(f"{url}: blocked by proxy (Tunnel connection failed: 403)", kind="proxy_denied")


N.check_reachable = blocked
s = vc.full_sand(vc.reset(vc.WORK / "v7" / "s"))
vc.seed_committed(s)
vc.synthetic_rasters(s)
vc.write_modis_stage(s, vc.synthetic_modis_table(s, noise_frac=0.19, seed=1))
vc.locked_reruns(s)
n = len(vc.runlog(s))
print("baseline: features exit", R.run(["features"], s), vc.statuses(s, n))

real = M._library_versions
M._library_versions = lambda: {**real(), "gdal": "9.9.9"}          # another environment's GDAL
print("\nlibraries changed: modis_points.json staleness:", result_staleness(s, read_json(s.path("results", "modis_points.json"))))
print("StaleModisError is a StaleInputError subclass:", issubclass(M.StaleModisError, StaleInputError))
n = len(vc.runlog(s))
print("run([features]) exit", R.run(["features"], s), {k: v[:150] for k, v in vc.statuses(s, n).items()})
n = len(vc.runlog(s))
print("run([repro_checks]) exit", R.run(["repro_checks"], s), {k: v[:110] for k, v in vc.statuses(s, n).items()})
print("   NPP row:", [(r["status"], r["note"][:120]) for r in vc.table(s)["rows"] if r["quantity"].startswith("NPP")])
n = len(vc.runlog(s))
print("`make features`-like run([modis_points, features]) exit", R.run(["modis_points", "features"], s),
      {k: v[:90] for k, v in vc.statuses(s, n).items()})

M._library_versions = real
meta = s.path("interim", "modis_points.meta.json")
print("\nafter the blocked modis_points run: sidecar exists:", meta.exists(), "| parquet exists:",
      s.path("interim", "modis_points.parquet").exists())
meta.unlink(missing_ok=True)                 # sidecar missing, parquet + result intact
print("sidecar missing (libraries back to the original): modis_points.json staleness:",
      result_staleness(s, read_json(s.path("results", "modis_points.json"))))
n = len(vc.runlog(s))
print("run([features]) exit", R.run(["features"], s), {k: v[:150] for k, v in vc.statuses(s, n).items()})
n = len(vc.runlog(s))
print("run([repro_checks]) exit", R.run(["repro_checks"], s), {k: v[:110] for k, v in vc.statuses(s, n).items()})
