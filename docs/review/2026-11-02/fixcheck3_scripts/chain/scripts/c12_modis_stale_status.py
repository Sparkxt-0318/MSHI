"""A MODIS table that modis_points.json still records as current but load_modis_points refuses (libraries
changed since the extraction; or the sidecar is gone): status of features vs repro_checks."""
import sys, json, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc, author
logging.basicConfig(level=logging.CRITICAL)
import mshi.run as R
import mshi.data.modis as M
from mshi.io import result_staleness, read_json
base = cc.SCR / "work" / "c12"
cc.reset(base)
sand = cc.full_sand("s", base=base)
cc.seed_committed(sand)
author.fake_fetch_rasters(sand)
author.fake_modis_stage(sand, author.fake_modis_values(sand))
print("features (baseline):", R.run(["features"], sand), cc.statuses(sand))
real = M._library_versions
M._library_versions = lambda: {**real(), "gdal": "9.9.9"}          # environment upgraded after the extraction
print("modis_points.json staleness:", result_staleness(sand, read_json(sand.path("results", "modis_points.json"))))
n = len(cc.runlog(sand))
code = R.run(["features"], sand)
print("features after a library change: exit", code, {k: v[:120] for k, v in cc.statuses(sand, n).items()})
n = len(cc.runlog(sand))
code = R.run(["repro_checks"], sand)
print("repro_checks, same state: exit", code, {k: v[:80] for k, v in cc.statuses(sand, n).items()},
      [(r["status"], r["note"][:90]) for r in cc.rows(sand) if r["quantity"].startswith("NPP")])
M._library_versions = real
sand.path("interim", "modis_points.meta.json").unlink()                  # sidecar lost, parquet + result intact
n = len(cc.runlog(sand))
code = R.run(["features"], sand)
print("features, sidecar missing: exit", code, {k: v[:120] for k, v in cc.statuses(sand, n).items()})
