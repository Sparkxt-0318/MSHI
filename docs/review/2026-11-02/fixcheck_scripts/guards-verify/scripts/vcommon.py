"""Shared helpers for the adversarial verification of the 'guards' remaining-problem claims (scratch only).

Run every script with: GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I -B <script>
"""
import copy
import os
import sys

sys.dont_write_bytecode = True
os.environ["GIT_OPTIONAL_LOCKS"] = "0"
REPO = "/home/user/MSHI"
SCR = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards-verify"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from pathlib import Path  # noqa: E402

from mshi.config import Config, load_config  # noqa: E402

WORK = Path(SCR) / "work"


def sandbox(work, edit=None, full=True) -> Config:
    """Config whose raw/interim/derived/results/figures all live under ``work``.

    full=True: out_root None and every output root an absolute scratch path, so mshi.run.run() treats the
    invocation as a normal (non-smoke) run and does run repro_checks / site_diagnostics / clean_test.
    full=False: the out_root sandbox used by tests/test_robustness.py (smoke semantics in run()).
    """
    cfg = load_config()
    data = copy.deepcopy(cfg.data)
    work = Path(work)
    data["paths"]["raw"] = str(work / "raw")
    if full:
        for k in ("interim", "derived", "results", "figures"):
            data["paths"][k] = str(work / k)
    if edit:
        edit(data)
    c = Config(data, source=cfg.source, out_root=None if full else work / "out")
    for k in ("interim", "derived", "results", "figures"):
        assert REPO not in str(c.path(k)) or not full, c.path(k)
    return c
