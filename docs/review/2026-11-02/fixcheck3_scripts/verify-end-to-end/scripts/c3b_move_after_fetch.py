"""Claim 3 (b): fetch results written in a plain layout, then raw/worldclim moved to another disk and symlinked
back. The result stays current, but require_outputs (what `features` calls) raises ValueError.

Run: GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 /home/user/MSHI/.venv/bin/python -I -B c3b_move_after_fetch.py V
Uses the sandbox V/c3/new_plain written by c3_symlink_subdir.py (new plain new_plain).
"""
import copy
import json
import shutil
import sys
from pathlib import Path

V = Path(sys.argv[1])
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config  # noqa: E402
from mshi.io import require_outputs, result_staleness  # noqa: E402
from mshi.data.rasters import worldclim_path  # noqa: E402

root = V / "c3" / "new_plain"
base = load_config()
data = copy.deepcopy(base.data)
for r in ("raw", "interim", "derived", "results", "figures"):
    data["paths"][r] = str(root / "sb" / r)
cfg = Config(data, source=base.source)
wc = root / "sb" / "raw" / "worldclim"
big = root / "bigdisk2" / "worldclim"
if not wc.is_symlink():
    big.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(wc), str(big))
    wc.symlink_to(big, target_is_directory=True)
obj = json.loads(cfg.path("results", "fetch_worldclim.json").read_text())
out = {"staleness_fetch_worldclim": result_staleness(cfg, obj)}
tifs = [worldclim_path(cfg, i) for i in range(1, 20)]
try:
    require_outputs(cfg, "fetch_worldclim.json", tifs)
    out["require_outputs"] = "ok"
except Exception as e:  # noqa: BLE001
    out["require_outputs"] = f"{type(e).__name__}: {e}"
print(json.dumps(out, indent=1))
(V / "logs" / "c3b_move_after_fetch.json").write_text(json.dumps(out, indent=1))
