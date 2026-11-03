"""_gate_status for the noise ceiling (needs site_build) and a gridded stage (needs all groups) under FAIL / STALE /
NOT RUN rows in each group, a DEVIATION row, a table without group keys, and a stale (other-config) table."""
import copy, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
from mshi.io import write_result
from mshi.run import _gate_status, ROW_GROUPS
base = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb/gate_matrix")
cfg0 = load_config(); d = copy.deepcopy(cfg0.data)
for root in ("raw", "interim", "derived", "results", "figures"):
    d["paths"][root] = str(base / root)
cfg = Config(d, source=cfg0.source)
def table(bad_group=None, status="PASS", nogroup=False):
    rows = []
    for g in ROW_GROUPS:
        for i in range(2):
            r = {"quantity": f"{g} {i}", "status": status if (g == bad_group and i == 0) else "PASS", "group": g}
            if nogroup:
                r.pop("group")
            rows.append(r)
    summ = {k: sum(r["status"] == k for r in rows) for k in ("PASS", "FAIL", "STALE", "NOT RUN", "DEVIATION", "INFO")}
    write_result(cfg, {"rows": rows, "summary": summ}, "reproduction_check.json")
for g in ROW_GROUPS:
    for st in ("FAIL", "STALE", "NOT RUN", "DEVIATION"):
        table(g, st)
        a = _gate_status(cfg, {}, [], ("site_build",)); b = _gate_status(cfg, {}, [], ROW_GROUPS)
        print(f"{st:9s} in {g:11s}: noise_ceiling -> {a[:60]:60s} | gridded -> {b[:60]}")
table("npp", "NOT RUN", nogroup=True)
print("rows without group keys, NOT RUN npp: noise ->", _gate_status(cfg, {}, [], ("site_build",))[:70])
table()
d2 = copy.deepcopy(d); d2["smoke"]["n_sites"] = 51          # another config: the table is no longer current
cfg2 = Config(d2, source=cfg0.source)
print("table from another config: noise ->", _gate_status(cfg2, {}, [], ("site_build",))[:90])
