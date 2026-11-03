"""Area D end-to-end, step 6: the reproduction gate per row group (mshi.run._gate_status / run), in-process on the
sandbox. Stage functions after the gate are replaced by stubs (the gate decision is taken before a stage runs),
so only the gate is exercised; repro_checks itself is real except where stated.

S1 (stored table, repro_checks not in the invocation): site_build rows PASS, locked_test rows NOT RUN
    -> noise_ceiling (needs site_build) should run, us_r2 (needs all groups) should be skipped.
S2 (repro_checks in the invocation, NPP row FAIL): npp_correlation is stubbed to r = 0.90 (outside 0.982 +- 0.01)
    -> repro_checks writes the table and raises ReproductionFailure (status error); what does noise_ceiling do?
S3 (same stored table as S2, repro_checks not in the invocation): what does noise_ceiling do now?
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
import mshi.analysis.noise_ceiling as NCm
import mshi.analysis.us_r2 as USm
import mshi.analysis.repro_checks as RCm
from mshi import run as RUN
from mshi.config import load_config
from mshi.io import read_json, write_result, require_current

cfg_path = Path(sys.argv[1])
calls = []
NCm.noise_ceiling = lambda cfg: calls.append("noise_ceiling") or {"stub": True}
USm.us_r2 = lambda cfg: calls.append("us_r2") or {"stub": True}


def statuses(names):
    cfg = load_config(cfg_path)
    calls.clear()
    code = RUN.run(names, cfg)
    log = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
    last = {r["stage"]: r["status"] for r in log[-len(names):]}
    return code, last, list(calls)


# S1 ---------------------------------------------------------------------------------------------------
cfg = load_config(cfg_path)
rc = read_json(cfg.path("results", "reproduction_check.json"))
rows = [dict(r, status="NOT RUN", v3=None) if r["group"] == "locked_test" else r for r in rc["rows"]]
summary = {s: sum(r["status"] == s for r in rows) for s in ["PASS", "FAIL", "DEVIATION", "STALE", "NOT RUN", "INFO"]}
md = cfg.path("results", "reproduction_check.md")
write_result(cfg, {"rows": rows, "npp_check": rc.get("npp_check"), "summary": summary}, "reproduction_check.json",
             outputs=[md])
print("S1 stored table summary:", summary)
print("S1 run(['noise_ceiling','us_r2']):", statuses(["noise_ceiling", "us_r2"]))

# S2 ---------------------------------------------------------------------------------------------------
real_npp = RCm.npp_correlation


def bad_npp(cfg):
    out = real_npp(cfg)
    return {**out, "pearson_r": 0.90}


RCm.npp_correlation = bad_npp
print("S2 run(['repro_checks','noise_ceiling','us_r2']):", statuses(["repro_checks", "noise_ceiling", "us_r2"]))
cfg = load_config(cfg_path)
rc = require_current(cfg, "reproduction_check.json")
print("S2 stored table summary:", rc["summary"],
      "| FAIL rows:", [(r["quantity"], r["group"]) for r in rc["rows"] if r["status"] == "FAIL"])
print("S2 site_build rows:", {r["status"] for r in rc["rows"] if r["group"] == "site_build"})

# S3 ---------------------------------------------------------------------------------------------------
print("S3 run(['noise_ceiling','us_r2']):", statuses(["noise_ceiling", "us_r2"]))
print("S3 _gate_status(site_build):", RUN._gate_status(load_config(cfg_path), {}, ["noise_ceiling"], ("site_build",)))
