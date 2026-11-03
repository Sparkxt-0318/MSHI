"""The per-group gate on the regenerated (current-code) reproduction table of the sandbox 'build':
which stages may run while the locked_test and npp rows are NOT RUN."""
import json, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A/scripts/orig")
from sbcfg import sandbox_cfg
from mshi.run import _gate_status, _stages, GATE
cfg = sandbox_cfg("build")
rc = json.loads(cfg.path("results", "reproduction_check.json").read_text())
print("table summary:", rc["summary"])
order = [s.name for s in _stages()]
for s in _stages():
    if order.index(s.name) > order.index(GATE):
        print(f"{s.name:24s} needs={s.needs} exploratory={s.exploratory} gate: {_gate_status(cfg, {}, [], s.needs)}")
