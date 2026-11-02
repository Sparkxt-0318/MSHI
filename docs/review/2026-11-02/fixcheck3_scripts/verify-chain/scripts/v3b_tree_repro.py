"""Claim 3: `make repro` on an exported tree (argv[1]). The Config keeps the tree's config data (same config hash)
but its results root is redirected to a scratch copy of the tree's results/, so nothing else is written."""
import json
import shutil
import sys
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(tree))
sys.dont_write_bytecode = True
import mshi  # noqa: E402

assert Path(mshi.__file__).resolve().is_relative_to(tree)
import logging  # noqa: E402

logging.basicConfig(level=logging.ERROR)
from mshi.config import Config, load_config  # noqa: E402
from mshi.run import run  # noqa: E402

shutil.rmtree(out, ignore_errors=True)
shutil.copytree(tree / "results", out)


class Redirected(Config):
    def path(self, root, *parts):
        if root == "results":
            return out.joinpath(*parts)
        return super().path(root, *parts)


base = load_config()
cfg = Redirected(base.data, source=base.source)
assert cfg.sha256() == base.sha256()
code = run(["repro_checks"], cfg)
rc = json.loads((out / "reproduction_check.json").read_text())
last = (out / "run_log.jsonl").read_text().splitlines()[-1]
print(tree.name, "| make repro exit", code, "| status", json.loads(last)["status"][:110])
print("summary", rc["summary"])
print("first STALE note:", next((r["note"] for r in rc["rows"] if r["status"] == "STALE"), None))
