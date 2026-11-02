"""Claim 7: do build_sites / site_diagnostics refuse raw inputs when no fetch_* result exists?
Sandbox (out_root) with NO fetch_srdb/fetch_naturalearth/fetch_cosore result. The committed COSORE table is
copied into the sandbox and recorded as the output of a sandbox cosore_annual.json (so build_sites' only
require_outputs check is satisfied). Reads data/raw (SRDB CSV, Natural Earth): run with python -I -B."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")

from mshi.config import Config, load_config  # noqa: E402
from mshi.io import write_result  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
root = SCR / "work" / "no_fetch"
shutil.rmtree(root, ignore_errors=True)
cfg = load_config()
sand = Config(cfg.data, source=cfg.source, out_root=root)

sand.path("derived").mkdir(parents=True)
csv = shutil.copy(cfg.path("derived", "cosore_annual.csv"), sand.path("derived", "cosore_annual.csv"))
c = json.loads(cfg.path("results", "cosore_annual.json").read_text())
write_result(sand, c, "cosore_annual.json", outputs=[Path(csv)])
print("sandbox results before:", sorted(p.name for p in sand.path("results").iterdir()))

from mshi.data.sites import build_sites  # noqa: E402
S = build_sites(sand)
print("build_sites OK without fetch results: records_after_qc", S["records_after_qc"], "sites_qc", S["sites_qc"]["n"],
      "sites_repo", S["sites_repo"]["n"])
from mshi.analysis.site_diagnostics import site_diagnostics  # noqa: E402
D = site_diagnostics(sand)
print("site_diagnostics OK without fetch_naturalearth.json; offland n", D["offland"]["n"])
print("sandbox results after:", sorted(p.name for p in sand.path("results").iterdir()))
fresh = json.loads(sand.path("results", "build_sites.json").read_text())["_outputs"]
committed = json.loads(cfg.path("results", "build_sites.json").read_text())["_outputs"]
print("sandbox build_sites _outputs == committed _outputs:", fresh == committed)
for name in ["fetch_srdb.json", "fetch_cosore.json", "fetch_naturalearth.json"]:
    d = json.loads(cfg.path("results", name).read_text())
    print("committed", name, "has _outputs:", "_outputs" in d, "| hash-like keys:",
          [k for k in d if "sha256" in k or k in ("commit", "tree")])
