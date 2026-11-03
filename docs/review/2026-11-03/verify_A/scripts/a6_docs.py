"""A-6 independent check (read-only). Instead of substring search: (1) for each committed data/derived file, the
committed result that records it as an output (its producer) and whether `make data` (make -n) runs that producer;
(2) rows of each file vs the rows the derived README states; (3) what the CC-BY 'changes made' note says vs the
analysis table's columns; (4) README status line date/phase vs HEAD's DECISIONS sections; (5) Makefile `all` help vs
the stage order of `--stage all`."""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/user/MSHI")
sys.path.insert(0, str(REPO))
import pandas as pd  # noqa: E402

res = {}
for p in sorted((REPO / "results").glob("*.json")):
    o = json.loads(p.read_text())
    for k in (o.get("_outputs") or {}):
        res.setdefault(k, []).append(p.name)
mk = subprocess.run(["make", "-n", "data"], cwd=REPO, capture_output=True, text=True).stdout
data_stages = [a for a in shlex.split(mk.replace("\\\n", " ")) if not a.startswith("-") and "/" not in a and a != "mshi.run"]
print("make data runs:", data_stages)
dr = (REPO / "data/derived/README.md").read_text()
documented = dict(re.findall(r"^\| `([^`]+)` \| ([\d,]+) \|", dr, re.M))
for f in sorted(x for x in (REPO / "data/derived").iterdir() if x.name != "README.md"):
    prod = res.get(f"derived:{f.name}", [])
    n = len(pd.read_csv(f)) if f.suffix == ".csv" else len(pd.read_parquet(f))
    stage = [x[:-5] for x in prod]
    print(f"  {f.name:28s} rows {n:5d} | producer {stage} | run by `make data`: {all(s in data_stages for s in stage)}"
          f" | row count in derived README: {documented.get(f.name, 'not listed')}")
note = [l for l in dr.splitlines() if l.startswith("Changes made")]
print("CC-BY 'changes made' note:", note)
cols = list(pd.read_csv(REPO / "data/derived/cosore_annual_analysis.csv", nrows=1).columns)
print("cosore_annual_analysis.csv columns:", cols)
print("main README line 74:", (REPO / "README.md").read_text().splitlines()[73])
print("README line 3:", (REPO / "README.md").read_text().splitlines()[2][:90])
heads = [l for l in (REPO / "docs/DECISIONS.md").read_text().splitlines() if l.startswith("## 2026-11-03")]
print("DECISIONS sections dated 2026-11-03:", heads)
mkall = [l for l in (REPO / "Makefile").read_text().splitlines() if l.startswith("all:")]
print("Makefile:", mkall)
lst = subprocess.run([str(REPO / ".venv/bin/python"), "-I", "-B", "-c", "import sys; sys.path.insert(0, '/home/user/MSHI'); from mshi.run import main; main(['--list'])"], cwd="/tmp",
                     capture_output=True, text=True).stdout.split("\n")
names = [l.split()[0] for l in lst if l.strip()]
print("--stage all runs after repro_checks:", names[names.index("repro_checks") + 1:])
