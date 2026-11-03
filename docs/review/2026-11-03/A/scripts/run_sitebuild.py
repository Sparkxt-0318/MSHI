"""Run the site-build stages (locked and analysis) with the CURRENT code into a scratch sandbox, then compare
the outputs with the committed ones (content only; provenance keys excluded)."""
import json
import logging
import sys
import time

sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/scripts")
from sbcfg import SCR, sandbox_cfg  # noqa: E402

import pandas as pd  # noqa: E402

from mshi.run import run  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
name = sys.argv[1] if len(sys.argv) > 1 else "build"
stages = sys.argv[2].split(",") if len(sys.argv) > 2 else ["cosore_annual", "cosore_annual_analysis", "build_sites",
                                                         "build_sites_analysis", "repro_checks"]
cfg = sandbox_cfg(name)
t = time.time()
rc = run(stages, cfg)
print("exit code", rc, "seconds", round(time.time() - t, 1))

REPO = "/home/user/MSHI"


def strip(o):
    return {k: v for k, v in o.items() if k not in ("_provenance", "_inputs", "_outputs")}


for f in ["cosore_annual.json", "cosore_annual_analysis.json", "build_sites.json", "build_sites_analysis.json",
          "reproduction_check.json"]:
    p = cfg.path("results", f)
    if not p.exists():
        print(f, "not produced")
        continue
    new = strip(json.loads(p.read_text()))
    old = strip(json.loads(open(f"{REPO}/results/{f}").read()))
    same = new == old
    print(f, "content identical to committed:", same)
    if not same:
        for k in sorted(set(new) | set(old)):
            if new.get(k) != old.get(k):
                print("   differs:", k, str(old.get(k))[:300], "->", str(new.get(k))[:300])

for f in ["cosore_annual.csv", "cosore_annual_analysis.csv", "records_v3.parquet", "sites_v3_qc.parquet",
          "sites_v3_repo.parquet", "records_analysis.parquet", "sites_analysis_qc.parquet", "sites_analysis_repo.parquet"]:
    p = cfg.path("derived", f)
    if not p.exists():
        print(f, "not produced")
        continue
    a = p.read_bytes()
    b = open(f"{REPO}/data/derived/{f}", "rb").read()
    if a == b:
        print(f, "bytes identical to committed")
        continue
    rd = pd.read_parquet if f.endswith(".parquet") else pd.read_csv
    x, y = rd(p), rd(f"{REPO}/data/derived/{f}")
    try:
        pd.testing.assert_frame_equal(x, y, check_dtype=True)
        print(f, "bytes differ but frames equal")
    except AssertionError as e:
        print(f, "FRAMES DIFFER:", str(e)[:500])
