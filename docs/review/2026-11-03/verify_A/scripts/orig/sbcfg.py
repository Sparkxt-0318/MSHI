"""Sandbox config helper for the area-A review: raw stays the repo's data/raw (read-only use), every output
root goes under the scratch directory. n_jobs capped at 2."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")

from mshi.config import Config, load_config  # noqa: E402

SCR = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/verify_A")


def sandbox_cfg(name: str, edit=None, raw_repo: bool = True) -> Config:
    cfg = load_config()
    data = copy.deepcopy(cfg.data)
    base = SCR / "sb" / name
    for root in ("interim", "derived", "results", "figures"):
        data["paths"][root] = str(base / root)
    if not raw_repo:
        data["paths"]["raw"] = str(base / "raw")
    else:
        data["paths"]["raw"] = str(Path("/home/user/MSHI/data/raw"))
    p2 = data["phase2"]
    p2["noise_ceiling"]["n_jobs"] = 2
    p2["transfer"]["rf"]["n_jobs"] = 2
    if edit:
        edit(data)
    return Config(data, source=cfg.source)
