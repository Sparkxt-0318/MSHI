"""Verifier's checks of D-3 (README Run section states the old whole-table gate) and D-4 (test_us_r2.settings()
docstring says configs/v3.yaml lacks keys it has). Reads the repository; writes only under argv[1]."""
import copy
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
import mshi.run as R
from mshi.analysis import us_r2 as U
from mshi.config import load_config
from mshi.io import write_result
from test_robustness import full_sandbox

REPO = Path("/home/user/MSHI")
cfg = load_config()
root = Path(sys.argv[1])

# ---------------------------------------------------------------- D-3
readme = (REPO / "README.md").read_text().splitlines()
print("README:25-27:", " ".join(x.strip() for x in readme[24:27]))
print("README:59-61:", " ".join(x.strip() for x in readme[58:61]))
rc = json.loads((REPO / "results/reproduction_check.json").read_text())
print("committed reproduction_check summary:", rc["summary"])
log = [json.loads(x) for x in (REPO / "results/run_log.jsonl").read_text().splitlines()]
nc = [r for r in log if r["stage"] == "noise_ceiling"]
for r in nc:
    print("committed run log noise_ceiling:", r["start_utc"], r["status"], "invocation", r.get("invocation"),
          "commit", r.get("git_commit"), "exploratory", r.get("exploratory"))
nc_res = json.loads((REPO / "results/noise_ceiling.json").read_text())
print("committed results/noise_ceiling.json exists; exploratory =", nc_res.get("exploratory"))

# a stored table with every site_build row PASS and the 10 gridded rows NOT RUN: does a later-phase stage run?
real = R._stages
ran = []
R._stages = lambda: [dataclasses.replace(s, func=(lambda n: (lambda c: ran.append(n) or {}))(s.name))
                     if s.name in ("noise_ceiling", "us_r2") else s for s in real()]
sand = full_sandbox(cfg, root / "d3")
rows = [dict(r) for r in rc["rows"]]                       # the committed rows: 17 PASS, 10 NOT RUN
write_result(sand, {"rows": rows, "npp_check": None, "summary": rc["summary"]}, "reproduction_check.json")
code = R.run(["noise_ceiling", "us_r2"], sand)
st = {json.loads(x)["stage"]: json.loads(x)["status"] for x in
      sand.path("results", "run_log.jsonl").read_text().splitlines()}
print(f"sandbox, committed rows (17 PASS, 10 NOT RUN): exit {code}; ran {ran}; statuses {st}")
R._stages = real

# ---------------------------------------------------------------- D-4
src = (REPO / "tests/test_us_r2.py").read_text().splitlines()
print("tests/test_us_r2.py:58-60:", " | ".join(x.strip() for x in src[57:60]))
U2 = cfg["phase2"]["us_r2"]
print("configs/v3.yaml phase2.us_r2 keys:", sorted(U2))
print("has train_continent/test_continent/xgb_seed_spread:",
      {k: U2.get(k) for k in ("train_continent", "test_continent", "xgb_seed_spread")})
S = U.Settings.from_cfg(cfg)                                # the committed config, no test edits
print("Settings.from_cfg(committed config) OK:", S.train_continent, "->", S.test_continent, "seeds", S.seed_spread,
      "bootstrap n", S.bootstrap["n"])
sys.path.insert(0, str(REPO / "tests"))
import test_us_r2 as TU                                     # noqa: E402
d = copy.deepcopy(cfg.data)
TU.settings(d)
diff = {k: (U2.get(k), d["phase2"]["us_r2"][k]) for k in d["phase2"]["us_r2"] if U2.get(k) != d["phase2"]["us_r2"][k]}
print("what settings() changes in phase2.us_r2 (committed, test):", diff,
      "| bootstrap n:", cfg["phase2"]["bootstrap"]["n"], "->", d["phase2"]["bootstrap"]["n"])
