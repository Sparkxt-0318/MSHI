"""A-4 independent check (synthetic six-continent sites of tests/test_transfer.py instead of the reviewer's 'chain'
sandbox; a different failure of features_analysis: its upstream build_sites_analysis.json is absent -> stale).

1. Declared deps (run.py) vs what within_continent actually reads (its result's _inputs).
2. Invocation [features_analysis, within_continent]: features_analysis fails; is within_continent skipped?
3. Invocation [features_analysis, transfer_matrix, within_continent] (as `make phase2`/`make all`): skipped?
4. Are the numbers within_continent produced in (2) the same as from a clean run (i.e. any wrong number)?
Smoke-type sandbox (out_root set) so the reproduction gate is not involved. Light settings."""
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from mshi import runlog  # noqa: E402

H = runlog.code_sha256()
runlog.code_sha256 = lambda pkg_dir=None: H          # freeze the code hash (another agent may edit the repo)
from mshi.config import load_config  # noqa: E402
import mshi.run as R  # noqa: E402
from mshi.analysis import transfer as T  # noqa: E402
from test_transfer import light, synth_sites, record_features, install_fakes  # noqa: E402
from test_robustness import sandbox  # noqa: E402

BASE = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/sb/a4")
import shutil  # noqa: E402
if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)
cfg0 = load_config()
sand = sandbox(cfg0, BASE, edit=light)
assert sand.out_root is not None
deps = {s.name: s.deps for s in R._stages()}
print("1. declared deps of within_continent:", deps["within_continent"], "| of transfer_matrix:", deps["transfer_matrix"])

mp = pytest.MonkeyPatch()
install_fakes(mp, sand)
record_features(sand, synth_sites(seed=5))
print("   transfer_matrix ->", R.run(["transfer_matrix"], sand), "; within_continent ->", R.run(["within_continent"], sand))
wc1 = json.loads(sand.path("results", "within_continent.json").read_text())
print("   within_continent.json _inputs:", sorted(wc1["_inputs"]))
b1 = sand.path("results", "within_continent.json").read_bytes()

code2 = R.run(["features_analysis", "within_continent"], sand)
log = [json.loads(x) for x in sand.path("results", "run_log.jsonl").read_text().splitlines()]
print("2. [features_analysis, within_continent]: exit", code2)
for r in log[-2:]:
    print(f"     {r['stage']:18s} {r['status'][:150]}")
b2 = sand.path("results", "within_continent.json").read_bytes()
print("   within_continent.json byte-identical to the clean run:", b1 == b2)

code3 = R.run(["features_analysis", "transfer_matrix", "within_continent"], sand)
log = [json.loads(x) for x in sand.path("results", "run_log.jsonl").read_text().splitlines()]
print("3. [features_analysis, transfer_matrix, within_continent]: exit", code3)
for r in log[-3:]:
    print(f"     {r['stage']:18s} {r['status'][:150]}")
mp.undo()
