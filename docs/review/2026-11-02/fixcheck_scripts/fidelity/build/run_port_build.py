"""Port stages cosore_annual -> build_sites -> site_diagnostics into a sandbox out_root, reading the pinned raw
inputs in /home/user/MSHI/data/raw (read-only)."""
import copy, sys, time
sys.dont_write_bytecode = True
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
from mshi.data.cosore import cosore_annual
from mshi.data.sites import build_sites
from mshi.analysis.site_diagnostics import site_diagnostics
cfg = load_config()
OUT = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/fidelity/build/port_out"
sand = Config(copy.deepcopy(cfg.data), source=cfg.source, out_root=OUT)
print("raw root:", sand.path("raw"), "| derived:", sand.path("derived"))
for f in (cosore_annual, build_sites, site_diagnostics):
    t = time.time(); f(sand); print(f.__name__, f"{time.time()-t:.1f}s")
