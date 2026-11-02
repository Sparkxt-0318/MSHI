"""Claim 5: a reproduction table whose rows are all STALE exits 0.

Sandbox = copy of the committed results/ and data/derived/. Config A (unchanged) vs config with an unrelated
edit (smoke.seed). Both through mshi.run.run() and through the CLI entry point mshi.run.main().
"""
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path, sandbox  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
import yaml  # noqa: E402

from mshi.io import read_json  # noqa: E402
from mshi.run import main, run  # noqa: E402


def prep(cfg):
    shutil.copytree(Path(REPO) / "results", cfg.path("results"))
    shutil.copytree(Path(REPO) / "data" / "derived", cfg.path("derived"))


def report(tag, cfg, code):
    rc = read_json(cfg.path("results", "reproduction_check.json"))
    last = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-1]
    print(f"[{tag}] exit {code}; run_log last record: stage={last['stage']} status={last['status']!r}; "
          f"summary {rc['summary']}")


W = WORK / "v5"; shutil.rmtree(W, ignore_errors=True)
a = sandbox(W / "A"); prep(a)
report("config A, run([repro_checks])", a, run(["repro_checks"], a))
b = sandbox(W / "B", edit=lambda d: d["smoke"].__setitem__("seed", 1)); prep(b)
report("smoke.seed edited, run([repro_checks])", b, run(["repro_checks"], b))

# CLI: a config file with the same edit and absolute scratch output paths
c_dir = W / "C"
data = yaml.safe_load(open(Path(REPO) / "configs" / "v3.yaml"))
data["smoke"]["seed"] = 1
for k in ("interim", "derived", "results", "figures"):
    data["paths"][k] = str(c_dir / k)
data["paths"]["raw"] = str(c_dir / "raw")
c_dir.mkdir(parents=True)
(c_dir / "cfg.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
shutil.copytree(Path(REPO) / "results", c_dir / "results")
shutil.copytree(Path(REPO) / "data" / "derived", c_dir / "derived")
code = main(["--stage", "repro_checks", "--config", str(c_dir / "cfg.yaml")])
rc = read_json(c_dir / "results" / "reproduction_check.json")
print(f"[CLI python -m mshi.run --stage repro_checks --config <smoke.seed edited>] exit {code}; summary {rc['summary']}")
print("   distinct row notes:", sorted({r['note'][:70] for r in rc['rows'] if r['status'] == 'STALE'}))
