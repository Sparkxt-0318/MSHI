import copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.CRITICAL)
from mshi.run import run
from mshi.io import sha256_file, result_staleness
from mshi.analysis import clean_test as CT
from mshi.config import Config

W = Path(SCR) / "work" / "t11"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
RAW = Path(REPO) / "data/raw"
cfg = sandbox(W, absolute=True)
cfg.path("raw", "srdb", "02163a72").mkdir(parents=True)
for f in ("srdb-data.csv", "LICENSE"):
    shutil.copy(RAW / "srdb/02163a72" / f, cfg.path("raw", "srdb", "02163a72", f))
cfg.path("raw", "naturalearth", "v5.1.2").mkdir(parents=True)
for f in cfg["sources"]["naturalearth"]["files"]:
    shutil.copy(RAW / "naturalearth/v5.1.2" / f, cfg.path("raw", "naturalearth", "v5.1.2", f))
cfg.path("derived").mkdir(parents=True)
shutil.copy(Path(REPO) / "data/derived/cosore_annual.csv", cfg.path("derived", "cosore_annual.csv"))
print("pinned licence sha256 matches file:", sha256_file(cfg.path("raw", "srdb", "02163a72", "LICENSE")) == cfg["sources"]["srdb"]["licence_sha256"])
dead = free_port()
for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
    os.environ[k] = f"http://127.0.0.1:{dead}"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = ""
code = run(["fetch_srdb", "fetch_naturalearth", "build_sites"], cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
print("offline (proxy -> dead port) fetch_srdb+fetch_naturalearth+build_sites: exit", code, [(r["stage"], r["status"][:60]) for r in recs])
cfg.path("raw", "srdb", "02163a72", "LICENSE").unlink()
code = run(["fetch_srdb", "build_sites"], cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-2:]
print("offline, LICENSE missing: exit", code, [(r["stage"], r["status"][:70]) for r in recs])

# locked result: a modified copy, with and without the config's sha256 field updated
base = load_config()
src = Path(REPO) / base["clean_test"]["locked_results"]["qc"]["file"]
alt = W / "clean_test_europe.json"; alt.write_text(src.read_text().replace('"n": 235', '"n": 236', 1))
for upd in (False, True):
    d = copy.deepcopy(base.data)
    d["clean_test"]["locked_results"]["qc"]["file"] = str(alt)
    if upd:
        d["clean_test"]["locked_results"]["qc"]["sha256"] = sha256_file(alt)
    try:
        CT.verify_lock(Config(d, source=base.source)); print("modified locked result, sha field updated:", upd, "-> PASSES")
    except CT.LockedPlanError as e:
        print("modified locked result, sha field updated:", upd, "-> refused")

# committed results vs current tree
for f in sorted((Path(REPO) / "results").glob("*.json")):
    o = json.loads(f.read_text())
    print(f"committed {f.name:28s} staleness: {result_staleness(base, o) if '_provenance' in o else 'no _provenance (environment record)'}")
