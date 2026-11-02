"""Drive mshi.analysis.repro_checks through every row state in sandboxes (out_root = scratch).
Re-run JSONs are copies of the locked results (nothing is scored); MODIS tables are synthetic."""
import copy, json, shutil, sys, traceback
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import Config, load_config
from mshi.io import write_result, read_json, StaleInputError, read_table
from mshi.analysis import repro_checks as RC
from mshi.analysis.clean_test import compare_with_locked
from mshi.data.modis import write_modis_cache, modis_cache_key, site_key

REPO = Path("/home/user/MSHI")
W = Path(sys.argv[1])
BASE = load_config()

def sandbox(name, data=None):
    sb = W / name
    shutil.rmtree(sb, ignore_errors=True)
    (sb / "results").mkdir(parents=True)
    for f in (REPO / "results").glob("*.json"):
        if not f.name.startswith("reproduction_check"):
            shutil.copy(f, sb / "results" / f.name)
    shutil.copy(REPO / "results" / "run_log.jsonl", sb / "results" / "run_log.jsonl")
    shutil.copytree(REPO / "data" / "derived", sb / "data" / "derived")
    return Config(copy.deepcopy(data or BASE.data), source=BASE.source, out_root=sb)

def other_cfg(cfg):
    d = cfg.data; d["smoke"]["seed"] = 1
    return Config(d, source=cfg.source, out_root=cfg.out_root)

def rerun(cfg, tag, mutate=None, vs=True, write_cfg=None):
    lr = cfg["clean_test"]["locked_results"][tag]
    R = read_json(cfg.repo_path(lr["file"]))
    R["variant"] = tag
    if mutate: mutate(R)
    if vs:
        R["vs_locked"] = compare_with_locked(R, read_json(cfg.repo_path(lr["file"])), cfg["clean_test"]["deviation_atol"])
    R["lock"] = {"locked_sha256": cfg["clean_test"]["locked_sha256"]}
    write_result(write_cfg or cfg, R, f"clean_test_rerun_{tag}.json")
    return R

def modis(cfg, npp_fn, n_failed=0, write_cfg=None):
    frames = [read_table(cfg, cfg.repo_path(r)) for r in cfg["legacy_allowlist"]]
    o = pd.concat(frames, ignore_index=True)
    keys = site_key(o.latitude, o.longitude, 5).values
    t = pd.DataFrame({"site_key": keys, "npp": npp_fn(o), "npp_n": 5}).drop_duplicates("site_key")
    rec = {"n_failed_reads": n_failed, "n_points": int(len(t))}
    out = write_modis_cache(cfg, t, modis_cache_key(cfg, t.site_key), rec)
    write_result(write_cfg or cfg, rec, "modis_points.json", outputs=[out])
    return out

def show(name, cfg, invocation=None):
    cfg.invocation = invocation
    try:
        res = RC.repro_checks(cfg); outcome = f"returned {res}"
    except Exception as e:
        outcome = f"RAISED {type(e).__name__}: {str(e)[:160]}"
    print(f"\n=== {name}: {outcome}")
    js = read_json(cfg.path("results", "reproduction_check.json"))
    print("summary", js["summary"])
    for r in js["rows"]:
        if r["quantity"].startswith(("Locked", "NPP", "Original", "COSORE")) or r["status"] not in ("PASS",):
            print(f"  {r['status']:9s} | {r['quantity'][:75]:75s} | v3={r['v3']!r} | tol={r['tolerance']} | note={r['note'][:120]!r}")
    return js

# --- S0: regenerate the committed table from the committed results + the a6c00bc invocation statuses
cfg = sandbox("S0")
recs = [json.loads(l) for l in (REPO / "results" / "run_log.jsonl").read_text().splitlines()]
inv = [r for r in recs if r.get("git_commit", "").startswith("a6c00bc")]
status = {r["stage"]: r["status"] for r in inv if r["stage"] != "repro_checks"}
show("S0 committed regen", cfg, {"stages": [r["stage"] for r in inv], "status": status})
for f in ["reproduction_check.md", "reproduction_check.json"]:
    a, b = (cfg.path("results", f)).read_bytes(), (REPO / "results" / f).read_bytes()
    print(f"  {f} byte-identical to committed: {a == b}")

# --- S1: repro-only invocation on the committed state (no invocation statuses)
show("S1 repro only, committed state", sandbox("S1"))

# --- S2: both re-runs identical
cfg = sandbox("S2"); rerun(cfg, "qc"); rerun(cfg, "repo"); show("S2 both re-runs identical", cfg)

# --- S3: repo re-run deviates (other model, lower r2)
cfg = sandbox("S3"); rerun(cfg, "qc")
def dev(R):
    R["selected"] = {**R["selected"], "set": "C8", "learner": "XGB"}; R["primary"]["r2"] -= 0.4
rerun(cfg, "repo", dev); show("S3 repo deviates", cfg)

# --- S4: repo re-run without vs_locked
cfg = sandbox("S4"); rerun(cfg, "qc"); rerun(cfg, "repo", vs=False); show("S4 repo without vs_locked", cfg)

# --- S5: malformed vs_locked (identical not a bool)
cfg = sandbox("S5"); rerun(cfg, "qc")
R = rerun(cfg, "repo"); R["vs_locked"]["identical"] = "yes"; write_result(cfg, R, "clean_test_rerun_repo.json")
show("S5 repo vs_locked.identical='yes'", cfg)

# --- S6: identical False and no primary diff
cfg = sandbox("S6"); rerun(cfg, "qc")
R = rerun(cfg, "repo"); R["vs_locked"] = {"identical": False, "selected_same": True, "max_abs_primary_diff": None}
write_result(cfg, R, "clean_test_rerun_repo.json"); show("S6 repo identical False, diff None", cfg)

# --- S7: repo re-run stale (another config)
cfg = sandbox("S7"); rerun(cfg, "qc"); rerun(cfg, "repo", write_cfg=other_cfg(cfg)); show("S7 repo stale", cfg)

# --- S8: repo stale and without vs_locked
cfg = sandbox("S8"); rerun(cfg, "qc"); rerun(cfg, "repo", vs=False, write_cfg=other_cfg(cfg)); show("S8 repo stale, no vs_locked", cfg)

# --- S9: FAIL (qc selects XGB) and STALE (repo) together -> raise order
cfg = sandbox("S9")
rerun(cfg, "qc", lambda R: R.__setitem__("selected", {**R["selected"], "set": "ALL", "learner": "XGB"}))
rerun(cfg, "repo", write_cfg=other_cfg(cfg)); show("S9 FAIL + STALE", cfg)

# --- S10: qc stale, repo missing
cfg = sandbox("S10"); rerun(cfg, "qc", write_cfg=other_cfg(cfg)); show("S10 qc stale, repo missing", cfg)

# --- N1: MODIS current, synthetic NPP equal to the committed NPP (r = 1.0 -> FAIL at 0.982 +- 0.01)
cfg = sandbox("N1"); modis(cfg, lambda o: o.npp.values); show("N1 modis current r=1", cfg)
# --- N1b: MODIS current, synthetic NPP with noise (r close to 0.98)
cfg = sandbox("N1b"); rng = np.random.default_rng(0)
modis(cfg, lambda o: o.npp.values + rng.normal(0, 0.19 * np.nanstd(o.npp.values), len(o))); show("N1b modis current noisy", cfg)
# --- N2: MODIS current, all NaN
cfg = sandbox("N2"); modis(cfg, lambda o: np.full(len(o), np.nan)); show("N2 modis current all-NaN", cfg)
# --- N3: modis_points.json from another config
cfg = sandbox("N3"); modis(cfg, lambda o: o.npp.values, write_cfg=other_cfg(cfg)); show("N3 modis_points.json stale", cfg)
# --- N4: current json, sidecar records a failed read
cfg = sandbox("N4"); modis(cfg, lambda o: o.npp.values, n_failed=1); show("N4 sidecar n_failed_reads 1", cfg)
# --- N5: parquet changed after the run
cfg = sandbox("N5"); p = modis(cfg, lambda o: o.npp.values)
t = pd.read_parquet(p); t["npp"] *= 2; t.to_parquet(p, index=False); show("N5 parquet changed", cfg)
# --- N6: incomplete modis_points.json, run log: error
cfg = sandbox("N6"); write_result(cfg, {"status": "incomplete: no values written", "n_failed_reads": 3}, "modis_points.json")
with open(cfg.path("results", "run_log.jsonl"), "a") as fh:
    fh.write(json.dumps({"stage": "modis_points", "status": "error: ModisIncompleteError: 3 of 10 MODIS raster reads failed", "end_utc": "2026-11-03T00:00:00+00:00"}) + "\n")
show("N6 incomplete + run-log error", cfg)
# --- N7: incomplete modis_points.json, no run-log record of modis_points
cfg = sandbox("N7"); write_result(cfg, {"status": "incomplete: no values written", "n_failed_reads": 3}, "modis_points.json")
(cfg.path("results", "run_log.jsonl")).write_text("")
show("N7 incomplete, empty run log", cfg)
print("\nlegend:", (W / "S2" / "results" / "reproduction_check.md").read_text().splitlines()[-1])
