"""Verifier's independent check of D-2 (per-group gate vs repro_checks in the same invocation).

Method differs from the reviewer's: no e2e sandbox; a full (non-smoke) sandbox with absolute temp paths, the REAL
repro_checks stage, upstream results recorded with write_result (site-build results = the committed content, so
the site_build rows PASS; locked-test re-runs = fake results with chosen values; no MODIS result, so the NPP rows are
NOT RUN), and the REAL stage list of mshi.run with only noise_ceiling and us_r2 replaced by recorders (the gate is
decided before a stage function is called). Scenarios:
  A  locked-test FAIL (Europe R2 off by 0.05), invocation [repro_checks, noise_ceiling, us_r2]
  B  the same stored table, invocation [noise_ceiling, us_r2]
  C  no locked-test result (NOT RUN rows only), invocation [repro_checks, noise_ceiling, us_r2]
  D  a STALE locked-test row (re-run recorded under another config), invocation [repro_checks, noise_ceiling, us_r2],
     then [noise_ceiling, us_r2]
  E  sanity: a site_build FAIL closes noise_ceiling in both invocation forms
Writes only under argv[1].
"""
import copy
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
import mshi.run as R
from mshi.config import Config, load_config
from mshi.io import write_result
from test_robustness import full_sandbox

cfg = load_config()
root = Path(sys.argv[1])
real_stages = R._stages
calls = []


def stub(name):
    def f(c):
        calls.append(name)
        return {"stub": name}
    return f


R._stages = lambda: [dataclasses.replace(s, func=stub(s.name)) if s.name in ("noise_ceiling", "us_r2") else s
                     for s in real_stages()]
print("needs:", {s.name: s.needs for s in R._stages() if s.name in ("noise_ceiling", "us_r2", "europe_geo_sensitivity")})


def committed(name):
    d = json.loads(cfg.path("results", name).read_text())
    d.pop("_provenance", None)
    for k in ("_outputs", "_inputs"):
        d.pop(k, None)
    return d


T = cfg["reproduction_targets"]["locked_test"]


def rerun(r2_shift=0.0):
    prim = {"n": T["europe_n"]["value"], "r2": T["europe_r2"]["value"] + r2_shift,
            "ci_site": [T["europe_ci_lo"]["value"], T["europe_ci_hi"]["value"]]}
    return {"selected": {"learner": T["selected"], "set": "TP", "cv_r2": T["asia_cv_r2"]["value"]}, "primary": prim,
            "vs_locked": {"identical": r2_shift == 0.0, "max_abs_primary_diff": abs(r2_shift), "selected_same": True}}


def setup(sub, ct=None, ct_cfg=None, site_fail=False):
    sand = full_sandbox(cfg, root / sub)
    bs = committed("build_sites.json")
    if site_fail:
        bs["sites_qc"]["n"] += 100
    write_result(sand, committed("cosore_annual.json"), "cosore_annual.json")
    write_result(sand, bs, "build_sites.json")
    if ct is not None:
        w = ct_cfg(sand) if ct_cfg else sand
        write_result(w, ct, "clean_test_rerun_qc.json")
        write_result(w, rerun(0.0), "clean_test_rerun_repo.json")
    return sand


def invoke(sand, names):
    calls.clear()
    c = Config(copy.deepcopy(sand.data), source=sand.source)      # a fresh process-like Config per invocation
    code = R.run(names, c)
    log = [json.loads(x) for x in c.path("results", "run_log.jsonl").read_text().splitlines()][-len(names):]
    rc = json.loads(c.path("results", "reproduction_check.json").read_text())
    groups = {}
    for r in rc["rows"]:
        groups.setdefault(r["group"], {}).setdefault(r["status"], 0)
        groups[r["group"]][r["status"]] += 1
    return code, {r["stage"]: r["status"][:150] for r in log}, list(calls), groups


def show(tag, out):
    code, st, ran, groups = out
    print(f"{tag}: exit {code}; ran {ran}")
    for k, v in st.items():
        print(f"    {k:14s} {v}")
    print(f"    stored table by group: {groups}")


A = setup("A", ct=rerun(0.05))
show("A [repro_checks, noise_ceiling, us_r2] (locked-test FAIL)", invoke(A, ["repro_checks", "noise_ceiling", "us_r2"]))
show("B [noise_ceiling, us_r2] (same stored table)", invoke(A, ["noise_ceiling", "us_r2"]))
print("B _gate_status(site_build):", R._gate_status(Config(copy.deepcopy(A.data), source=A.source), {},
                                                     ["noise_ceiling"], ("site_build",)))

C = setup("C")
show("C [repro_checks, noise_ceiling, us_r2] (NOT RUN rows only)", invoke(C, ["repro_checks", "noise_ceiling", "us_r2"]))


def other_cfg(sand):        # the re-run recorded under another config: STALE in this sandbox
    d = copy.deepcopy(sand.data)
    d["smoke"]["seed"] += 1
    return Config(d, source=sand.source)


Dd = setup("D", ct=rerun(0.0), ct_cfg=other_cfg)
show("D1 [repro_checks, noise_ceiling, us_r2] (locked-test STALE)", invoke(Dd, ["repro_checks", "noise_ceiling", "us_r2"]))
show("D2 [noise_ceiling, us_r2] (same stored table)", invoke(Dd, ["noise_ceiling", "us_r2"]))

E = setup("E", ct=rerun(0.0), site_fail=True)
show("E1 [repro_checks, noise_ceiling, us_r2] (site_build FAIL)", invoke(E, ["repro_checks", "noise_ceiling", "us_r2"]))
show("E2 [noise_ceiling, us_r2] (same stored table)", invoke(E, ["noise_ceiling", "us_r2"]))
