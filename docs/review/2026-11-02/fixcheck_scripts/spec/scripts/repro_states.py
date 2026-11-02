"""Exercise mshi.analysis.repro_checks in many states, in a scratch sandbox (out_root)."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd
from mshi.config import load_config, Config, canonical_sha256
from mshi.io import write_result, write_json, read_table, write_table
from mshi.data import modis as M
from mshi.analysis import repro_checks as RC

SCR = Path(sys.argv[1])
base = load_config()

def sandbox(name, edit=None, wipe=True):
    d = copy.deepcopy(base.data)
    d["paths"]["raw"] = str(SCR / name / "raw")
    if edit: edit(d)
    root = SCR / name / "out"
    if wipe and root.exists(): shutil.rmtree(root)
    return Config(d, source=base.source, out_root=root)

def committed(name):
    o = json.loads(base.path("results", name).read_text()); o.pop("_provenance", None); return o

def put_build(c):
    for f in ["build_sites.json", "cosore_annual.json"]:
        write_result(c, committed(f), f)

def put_modis(c, npp_noise=0.12, overlap=True):
    # synthetic MODIS cache from the committed v2 NPP (scaled), with the current key
    frames = [read_table(c, c.repo_path(rel)) for rel in c["legacy_allowlist"]]
    o = pd.concat(frames, ignore_index=True)
    keys = M.site_key(o.latitude, o.longitude, c["features"]["site_key_round"]).values
    rng = np.random.default_rng(0)
    npp = o.npp.values * 0.1 * (1 + rng.normal(0, npp_noise, len(o)))
    if not overlap:
        keys = np.array([k + "x" for k in keys])
    df = pd.DataFrame({"site_key": keys, "npp": npp, "npp_n": 5, "lst_day": 20.0, "lst_day_n": 60,
                       "lst_night": 5.0, "lst_night_n": 60})
    key = M.modis_cache_key(c, df.site_key)
    rec = {"n_points": len(df), "n_failed_reads": 0, "failed_reads": [], "cache_key": key}
    out, meta = M._paths(c)
    write_table(df, out)
    write_json({"key": key, "record": rec}, meta)
    write_result(c, rec, "modis_points.json")

def put_rerun(c, n=235, r2=0.079, lo=0.013, hi=0.125, vs="identical", sel="OLS-TP"):
    R = {"selected": {"set": "TP", "learner": sel, "cv_r2": 0.143},
         "primary": {"n": n, "r2": r2, "ci_site": [lo, hi]}, "lock": {"locked_sha256": "x"}}
    if vs == "identical":
        R["vs_locked"] = {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}
    elif vs == "deviation":
        R["vs_locked"] = {"identical": False, "selected_same": True, "max_abs_primary_diff": 3e-4}
    elif vs == "none_diff":
        R["vs_locked"] = {"identical": False, "selected_same": False, "max_abs_primary_diff": None}
    write_result(c, R, "clean_test_rerun_qc.json")

def runlog(c, recs):
    p = c.path("results", "run_log.jsonl"); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        for r in recs: fh.write(json.dumps(r) + "\n")

def show(tag, c, invocation=None):
    c.invocation = invocation
    try:
        s = RC.repro_checks(c); exc = None
    except Exception as e:
        s, exc = None, f"{type(e).__name__}: {str(e)[:160]}"
    rows = []
    p = c.path("results", "reproduction_check.json")
    if p.exists():
        rows = json.loads(p.read_text())["rows"]
    print(f"\n=== {tag}: summary={s} exc={exc}")
    for r in rows:
        if r["quantity"].startswith(("Locked", "NPP", "Original", "COSORE", "SRDB")):
            print(f"  {r['status']:9s} | {r['quantity'][:55]:55s} | v3={r['v3']!r} | note={r['note'][:120]!r}")

# A: invocation None, build files current, nothing else, no run log
c = sandbox("A"); put_build(c); show("A none/no-log", c)
# B: modis_points.json incomplete + run log error
c = sandbox("B"); put_build(c)
write_result(c, {"n_failed_reads": 3, "status": "incomplete: no values written"}, "modis_points.json")
runlog(c, [{"stage": "modis_points", "status": "error: ModisIncompleteError: 3 of 10 reads failed", "end_utc": "2026-11-02T10:00:00+00:00"}])
show("B incomplete + log error", c)
# C: modis_points.json incomplete + no run log record
c = sandbox("C"); put_build(c)
write_result(c, {"n_failed_reads": 3, "status": "incomplete: no values written"}, "modis_points.json")
show("C incomplete, no log", c)
# C2: incomplete + run-log last record ok (e.g. older successful run, log of other machine)
c = sandbox("C2"); put_build(c)
write_result(c, {"n_failed_reads": 3, "status": "incomplete: no values written"}, "modis_points.json")
runlog(c, [{"stage": "modis_points", "status": "ok", "end_utc": "2026-11-02T10:00:00+00:00"}])
show("C2 incomplete, log ok", c)
# D: modis OK, rerun identical
c = sandbox("D"); put_build(c); put_modis(c); put_rerun(c); show("D all ok (invocation None)", c)
# D2: same but invocation from run() with all ok statuses
st = {s: "ok" for s in ["fetch_srdb","fetch_cosore","fetch_naturalearth","cosore_annual","build_sites","site_diagnostics","fetch_worldclim","fetch_soilgrids","modis_points","features","clean_test"]}
show("D2 all ok (invocation all ok)", c, {"stages": list(st)+["repro_checks"], "status": dict(st)})
# E: stale modis_points.json (results written under a different config)
c = sandbox("E"); put_build(c); put_modis(c); put_rerun(c)
c2 = sandbox("E", edit=lambda d: d["smoke"].__setitem__("seed", 1), wipe=False)
# rewrite only build/cosore/rerun with c2 provenance so only modis json is stale vs c2... (modis written under c)
for f in ["build_sites.json", "cosore_annual.json"]:
    write_result(c2, committed(f), f)
put_rerun(c2)
show("E modis_points.json stale (other config)", c2)
# F: rerun without vs_locked
c = sandbox("F"); put_build(c); put_modis(c); put_rerun(c, vs=None); show("F rerun lacks vs_locked", c)
# G: deviation
c = sandbox("G"); put_build(c); put_modis(c); put_rerun(c, r2=0.0795, vs="deviation"); show("G deviation", c)
# H: Europe n 236
c = sandbox("H"); put_build(c); put_modis(c); put_rerun(c, n=236, vs="deviation"); show("H europe n 236", c)
# I: vs_locked identical False, max diff None
c = sandbox("I"); put_build(c); put_modis(c); put_rerun(c, vs="none_diff", sel="XGB"); show("I max diff None", c)
# J: NPP computed but no overlap -> pearson None
c = sandbox("J"); put_build(c); put_modis(c, overlap=False); put_rerun(c); show("J npp no overlap", c)
# K: NPP poor correlation -> FAIL
c = sandbox("K"); put_build(c); put_modis(c, npp_noise=0.8); put_rerun(c); show("K npp poor r", c)
# L: invocation: clean_test skipped
c = sandbox("L"); put_build(c); put_modis(c); put_rerun(c)
show("L clean_test skipped in invocation", c, {"stages": ["features","clean_test","repro_checks"], "status": {"features": "error: RuntimeError: x", "clean_test": "skipped: upstream features not available"}})
