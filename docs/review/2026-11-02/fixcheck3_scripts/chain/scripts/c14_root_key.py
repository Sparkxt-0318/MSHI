"""root_key / from_root_key: smoke out_root, nested roots, relative paths, symlinked root, outside every root."""
import sys, os, copy
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc
from pathlib import Path
from mshi.config import Config
base = cc.SCR / "work" / "c14"; cc.reset(base)
smoke = Config(copy.deepcopy(cc.CFG.data), source=cc.CFG.source, out_root=cc.CFG.path("interim", "smoke"))
for p in [smoke.path("derived", "sites_v3_qc.parquet"), smoke.path("results", "reproduction_check.md"),
          smoke.path("raw", "worldclim", "x.tif")]:
    k = smoke.root_key(p); print("smoke", k, smoke.from_root_key(k) == p)
d = copy.deepcopy(cc.CFG.data); d["paths"].update(interim=str(base / "data"), derived=str(base / "data" / "derived"))
nested = Config(d, source=cc.CFG.source)
k = nested.root_key(base / "data" / "derived" / "t.parquet"); print("nested", k, nested.from_root_key(k))
os.chdir(base)
real = Config(copy.deepcopy(cc.CFG.data), source=cc.CFG.source)
try:
    print("relative arg from another cwd:", real.root_key("data/derived/sites_v3_qc.parquet"))
except ValueError as e:
    print("relative arg from another cwd: ValueError", str(e)[:80])
os.symlink(base / "data", base / "link_root")
d2 = copy.deepcopy(cc.CFG.data); d2["paths"]["interim"] = str(base / "link_root")
sl = Config(d2, source=cc.CFG.source)
k = sl.root_key(base / "data" / "m.parquet"); print("symlinked root, real path:", k, sl.from_root_key(k))
try:
    print(real.root_key("/etc/hostname"))
except ValueError as e:
    print("outside every root: ValueError", str(e)[:60])
