"""MODIS cache key vs a concurrent edit of mshi/data/modis.py (scratch copy of the package only).

python -I -B race.py SCR PKGCOPY SANDBOX MODE
  MODE edit  : run stages up to features; at the start of cosore_annual (i.e. after the package was imported
               and before modis_points computes its cache key) modis.py of PKGCOPY is edited so that
               aggregate() doubles every window mean (a value-changing edit made by "another session").
  MODE plain : same stages, no edit (second run with the edited code now on disk, or a fresh sandbox).
Prints the run's stage statuses, whether modis_points was a cache hit, and the cached NPP at a few sites.
"""
import sys

SCR, PKG, SB, MODE = sys.argv[1:5]
sys.path.insert(0, SCR + "/scripts")
import e2e_lib as E  # noqa: E402  (inserts /home/user/MSHI; PKG goes in front of it below)

sys.path.insert(0, PKG)
import json  # noqa: E402
import logging  # noqa: E402
from pathlib import Path  # noqa: E402

import mshi  # noqa: E402

assert mshi.__file__.startswith(PKG), mshi.__file__
logging.basicConfig(level=logging.WARNING)
E.install()
from mshi.data import cosore as CO  # noqa: E402
from mshi.data import modis as M  # noqa: E402
from mshi.run import run  # noqa: E402

mod = Path(PKG) / "mshi/data/modis.py"
if MODE == "edit":
    real = CO.cosore_annual

    def cosore_annual_then_edit(cfg):
        s = mod.read_text()
        old = "            acc.setdefault((k, kind), []).append(val)\n"
        assert s.count(old) == 1
        mod.write_text(s.replace(old, "            acc.setdefault((k, kind), []).append(2 * val)\n"))
        print("edited", mod, "while the run was in progress", flush=True)
        return real(cfg)
    CO.cosore_annual = cosore_annual_then_edit

cfg = E.make_cfg(Path(SB))
names = ["fetch_srdb", "fetch_cosore", "fetch_naturalearth", "cosore_annual", "build_sites", "modis_points", "features"]
code = run(names, cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-len(names):]
print("exit", code, [(r["stage"], r["status"][:80], (r.get("result") or {}).get("cached")) for r in recs])
meta = json.loads(cfg.path("interim", "modis_points.meta.json").read_text())
import hashlib  # noqa: E402
import pandas as pd  # noqa: E402

print("aggregate() in memory doubles:", "2 * val" in __import__("inspect").getsource(M.aggregate))
print("cache key code_sha256", meta["key"]["code_sha256"][:12], "| sha256 of modis.py on disk now",
      hashlib.sha256(mod.read_bytes()).hexdigest()[:12])
df = pd.read_parquet(cfg.path("interim", "modis_points.parquet")).sort_values("site_key").head(3)
print("cached npp", df[["site_key", "npp"]].round(4).values.tolist())
f = pd.read_parquet(cfg.path("interim", "features_v3_qc.parquet"))
print("features npp (first 3 qc sites)", f.npp.round(4).head(3).tolist())
print("staleness", {k: v for k, v in E.staleness_report(cfg).items() if k in ("modis_points.json", "features.json")})
