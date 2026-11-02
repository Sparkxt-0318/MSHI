"""Provenance is per stage: build_sites run under config B on a cosore_annual.csv produced under config A."""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.CRITICAL)
import mshi.netutil as N
N.verify_git_checkout = lambda dest, commit: {"commit": commit, "tree": "-"}     # no git inside data/raw
from mshi.run import run
from mshi.io import result_staleness
RAW = Path(REPO) / "data/raw"
W = Path(SCR) / "work" / "t15"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
def seed(cfg):
    cfg.path("raw", "srdb", "02163a72").mkdir(parents=True, exist_ok=True)
    for f in ("srdb-data.csv", "LICENSE"):
        shutil.copy(RAW / "srdb/02163a72" / f, cfg.path("raw", "srdb", "02163a72", f))
    cfg.path("raw", "naturalearth", "v5.1.2").mkdir(parents=True, exist_ok=True)
    shutil.copy(RAW / "naturalearth/v5.1.2/ne_50m_admin_0_countries.geojson", cfg.path("raw", "naturalearth", "v5.1.2"))
    cfg.path("raw", "cosore").mkdir(parents=True, exist_ok=True)
    os.symlink(RAW / "cosore/02f32e8e", cfg.path("raw", "cosore", "02f32e8e"))
B = lambda d: d["cosore_annual"].__setitem__("rs_range", [50.0, 1000.0])
# what config B would give if the whole chain ran (separate sandbox)
full = sandbox(W / "fullB", edit=B, absolute=True); seed(full)
print("config B, cosore_annual + build_sites: exit", run(["cosore_annual", "build_sites"], full))
fb = json.loads(full.path("results", "build_sites.json").read_text())
# partial run under config B: cosore_annual.csv on disk is the committed one (config A)
part = sandbox(W / "partB", edit=B, absolute=True); seed(part)
part.path("derived").mkdir(parents=True)
shutil.copy(Path(REPO) / "data/derived/cosore_annual.csv", part.path("derived", "cosore_annual.csv"))
print("config B, build_sites + repro_checks on the config-A cosore_annual.csv: exit", run(["build_sites", "repro_checks"], part))
pb = json.loads(part.path("results", "build_sites.json").read_text())
for k in ("cosore_records", "records_after_qc"):
    print(f"   {k:20s} full chain B: {fb[k]:5d} | partial run B: {pb[k]:5d}")
print("   QC sites by continent, full B vs partial B:", fb["sites_qc"]["by_continent"], pb["sites_qc"]["by_continent"])
print("   partial-run build_sites.json staleness under config B:", result_staleness(part, pb))
rc = json.loads(part.path("results", "reproduction_check.json").read_text())
print("   repro summary (partial):", rc["summary"], "| COSORE row:", [(r["status"], r["note"][:40]) for r in rc["rows"][:1]])
