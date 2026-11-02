"""build_sites with no fetch_srdb.json / fetch_naturalearth.json in the sandbox: the raw inputs are checked
against pinned SHA-256s, not against a current upstream result (scratch copy of the repo; out_root sandbox)."""
import shutil, sys
from pathlib import Path
REPO = Path(sys.argv[1]); SB = Path(sys.argv[2]); sys.path.insert(0, str(REPO))
from mshi.config import load_config
from mshi.data.sites import build_sites
shutil.rmtree(SB, ignore_errors=True); (SB / "results").mkdir(parents=True); (SB / "data" / "derived").mkdir(parents=True)
shutil.copy(REPO / "results" / "cosore_annual.json", SB / "results")
shutil.copy(REPO / "data" / "derived" / "cosore_annual.csv", SB / "data" / "derived")
cfg = load_config(out_root=SB)
print("fetch_* results in sandbox:", sorted(p.name for p in (SB / "results").glob("fetch_*")))
S = build_sites(cfg)
print("build_sites ran: sites_qc", S["sites_qc"]["n"], "records_after_qc", S["records_after_qc"])
