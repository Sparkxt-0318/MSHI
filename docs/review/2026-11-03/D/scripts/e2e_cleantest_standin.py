"""Area D end-to-end, step 3: stand-ins for the locked-test re-runs (clean_test_rerun_{qc,repo}.json), as if the
re-run on real features had reproduced the locked results exactly. Written with mshi.io.write_result, reading
features.json through require_current (as the real stage does). Synthetic rasters cannot reproduce the locked
test, so without these the gate would stay closed; this simulates the state after a successful `make all`.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.analysis.clean_test import compare_with_locked
from mshi.io import read_json, require_current, write_result

cfg = load_config(Path(sys.argv[1]))
require_current(cfg, "features.json")
lr = cfg["clean_test"]["locked_results"]
for tag in cfg["clean_test"]["variants"]:
    locked = read_json(cfg.repo_path(lr[tag]["file"]))
    R = {k: v for k, v in locked.items()}
    R["variant"] = tag
    R["STAND_IN"] = "copy of the locked result written by the area-D reviewer's sandbox (not a re-run)"
    R["vs_locked"] = compare_with_locked(R, locked, cfg["clean_test"]["deviation_atol"])
    write_result(cfg, R, f"clean_test_rerun_{tag}.json", inputs=["features.json"])
    print(tag, R["vs_locked"]["identical"])
