"""Call tests/test_guards.py::test_reproduction_targets_are_the_briefs with loosened configs (scratch copy)."""
import copy, sys
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path[:0] = [str(REPO), str(REPO / "tests")]
import test_guards as TG
from mshi.config import Config, load_config
base = load_config()
def edit(fn):
    d = copy.deepcopy(base.data); fn(d["reproduction_targets"]); return Config(d, source=base.source)
cases = {"unmodified": lambda T: None,
         "europe_n rel 0.02": lambda T: T["locked_test"].__setitem__("europe_n", {"value": 235, "rel": 0.02}),
         "npp abs 0.05": lambda T: T["npp_corr_original_sites"].__setitem__("abs", 0.05),
         "srdb abs 1": lambda T: T["srdb_repo_filter_records"].__setitem__("abs", 1),
         "selected XGB": lambda T: T["locked_test"].__setitem__("selected", "XGB"),
         "int->float 4771.0": lambda T: T["srdb_repo_filter_records"].__setitem__("value", 4771.0)}
for name, fn in cases.items():
    try:
        TG.test_reproduction_targets_are_the_briefs(edit(fn)); print(f"{name:22s} test PASSES")
    except AssertionError:
        print(f"{name:22s} test FAILS")
print("BRIEF_ROWS found in PROMPT:", all(r in (REPO / "docs/handoff/PROMPT_mshi_v3.md").read_text() for r in TG.BRIEF_ROWS),
      "n rows", len(TG.BRIEF_ROWS))
import re
sec = (REPO / "docs/handoff/PROMPT_mshi_v3.md").read_text().split("### Reproduction targets")[1].split("Also add")[0]
rows = [l for l in sec.splitlines() if l.startswith("| ") and not l.startswith("| Quantity") and not l.startswith("|---")]
print("rows in PROMPT section 4 table:", len(rows), "all in BRIEF_ROWS:", all(any(l.startswith(b[:-1].rsplit('|',1)[0]) or l == b for b in TG.BRIEF_ROWS) for l in rows))
for l in rows: print("  ", l in TG.BRIEF_ROWS, l[:110])
