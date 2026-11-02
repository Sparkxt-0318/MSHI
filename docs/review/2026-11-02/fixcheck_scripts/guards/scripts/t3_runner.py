"""Runner statuses, exit codes, staleness and environment.json on a full (non-smoke) scratch sandbox."""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import logging
logging.basicConfig(level=logging.WARNING)
from mshi.run import run

W = Path(SCR) / "work" / "t3"
shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
REPO_RAW = Path(REPO) / "data" / "raw"

def mk(edit=None):
    cfg = sandbox(W, edit=edit, absolute=True)
    return cfg

def seed_inputs(cfg):
    (cfg.path("raw", "srdb", "02163a72")).mkdir(parents=True, exist_ok=True)
    for f in ("srdb-data.csv", "LICENSE"):
        shutil.copy(REPO_RAW / "srdb" / "02163a72" / f, cfg.path("raw", "srdb", "02163a72", f))
    cfg.path("raw", "naturalearth", "v5.1.2").mkdir(parents=True, exist_ok=True)
    for f in ("ne_50m_admin_0_countries.geojson", "ne_110m_land.geojson", "ne_50m_land.geojson"):
        shutil.copy(REPO_RAW / "naturalearth" / "v5.1.2" / f, cfg.path("raw", "naturalearth", "v5.1.2", f))
    cfg.path("derived").mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(REPO) / "data/derived/cosore_annual.csv", cfg.path("derived", "cosore_annual.csv"))

def log_tail(cfg, n):
    recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
    return [(r["stage"], r["status"][:110]) for r in recs[-n:]]

def repro_rows(cfg):
    d = json.loads(cfg.path("results", "reproduction_check.json").read_text())
    return d["summary"], [(r["quantity"], r["status"], r.get("note", "")[:90]) for r in d["rows"]]

cfg = mk(); seed_inputs(cfg)
print("A. build_sites + repro_checks (fresh sandbox): exit", run(["repro_checks", "build_sites"], cfg))
print("   log:", log_tail(cfg, 2))
s, rows = repro_rows(cfg); print("   summary:", s)
print("   environment.json written (non-full)?", cfg.path("results", "environment.json").exists())
bs_json = cfg.path("results", "build_sites.json").read_text()

# B. the raw SRDB file is corrupted -> build_sites must refuse; this invocation's rows must not PASS from the old file
p = cfg.path("raw", "srdb", "02163a72", "srdb-data.csv")
good = p.read_bytes()
p.write_bytes(good[: len(good) // 2])
print("B. corrupted SRDB, build_sites+repro_checks: exit", run(["build_sites", "repro_checks"], cfg))
print("   log:", log_tail(cfg, 2))
s, rows = repro_rows(cfg); print("   summary:", s); print("   first build row:", rows[1])
print("   build_sites.json unchanged:", cfg.path("results", "build_sites.json").read_text() == bs_json)

# C. later invocation: repro_checks alone (the last build_sites attempt failed, the old file has current provenance)
print("C. repro_checks alone after the failed build: exit", run(["repro_checks"], cfg))
s, rows = repro_rows(cfg); print("   summary:", s, "| first build row:", rows[1])

# D. single-stage build_sites with the corrupted raw file (documented single-stage workflow)
print("D. --stage build_sites alone with corrupted SRDB: exit", run(["build_sites"], cfg), log_tail(cfg, 1))
p.write_bytes(good)

# E. SRDB url -> local 404: error, not 'blocked'; note says error (DownloadError)
srv, base = serve()
def e404(d):
    d["sources"]["srdb"]["url"] = base + "/missing/{commit}/{file}"
cfg404 = mk(e404)
shutil.rmtree(cfg404.path("raw", "srdb"))
print("E. SRDB url 404, fetch_srdb+repro_checks: exit", run(["fetch_srdb", "repro_checks"], cfg404))
print("   log:", log_tail(cfg404, 2))
s, rows = repro_rows(cfg404); print("   summary:", s); print("   build row:", rows[1])

# F. config change after a successful run -> STALE rows; exit code?
cfg.path("raw", "srdb", "02163a72").mkdir(parents=True, exist_ok=True); seed_inputs(cfg)
print("F0. rebuild:", run(["build_sites"], cfg))
cfgF = mk(lambda d: d["smoke"].__setitem__("seed", 7))     # unrelated key: whole-config hash changes
print("F. repro_checks after an unrelated config change: exit", run(["repro_checks"], cfgF))
s, rows = repro_rows(cfgF); print("   summary:", s, rows[1])

# G. a FAIL row stops the run (exit 1)
cfgG = mk(lambda d: d["reproduction_targets"]["srdb_repo_filter_records"].__setitem__("value", 4770))
print("G. build_sites+repro_checks with a target outside tolerance: exit", run(["build_sites", "repro_checks"], cfgG))
print("   log:", log_tail(cfgG, 1))

# H. full=True writes environment.json; non-full never does
print("H. environment.json before full run:", cfg.path("results", "environment.json").exists())
print("   full run of a cheap subset -> exit", run(["build_sites"], cfg, full=True),
      "env written:", cfg.path("results", "environment.json").exists())
print("   env:", {k: (v if k != "versions" else "...") for k, v in json.loads(cfg.path("results", "environment.json").read_text()).items()})
srv.shutdown()
