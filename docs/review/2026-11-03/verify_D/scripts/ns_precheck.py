"""Inside the namespace: the copied sandbox's results are current and writes land in the copy."""
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.io import require_current
cfg = load_config(sys.argv[1])
for f in ("build_sites_analysis.json", "reproduction_check.json", "cosore_annual.json", "build_sites.json",
          "clean_test_rerun_qc.json", "modis_points.json"):
    try:
        require_current(cfg, f)
        print(f, "current")
    except Exception as e:  # noqa: BLE001
        print(f, "NOT current:", type(e).__name__, str(e)[:200])
marker = cfg.path("results", "_verifier_marker.txt")
marker.write_text("written inside the namespace\n")
print("marker written at", marker)
