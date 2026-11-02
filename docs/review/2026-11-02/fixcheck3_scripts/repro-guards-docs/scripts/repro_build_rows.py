"""Build rows: FAIL (srdb 4770 in a current build_sites.json) and STALE (cosore_annual.json from another config)."""
import copy, shutil, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
from mshi.io import write_result, read_json
from mshi.analysis import repro_checks as RC
REPO = Path("/home/user/MSHI"); W = Path(sys.argv[1]); B = load_config()
def sb(name):
    s = W / name; shutil.rmtree(s, ignore_errors=True); (s / "results").mkdir(parents=True)
    shutil.copytree(REPO / "data" / "derived", s / "data" / "derived")
    return Config(copy.deepcopy(B.data), source=B.source, out_root=s)
c = sb("B1")
b = read_json(REPO / "results" / "build_sites.json"); b["srdb_repo_filter_records"] = 4770
write_result(c, b, "build_sites.json", outputs=[c.path("derived", f) for f in ["records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet"]])
o = copy.deepcopy(B.data); o["smoke"]["seed"] = 1
write_result(Config(o, source=B.source, out_root=c.out_root), read_json(REPO / "results" / "cosore_annual.json"), "cosore_annual.json",
             outputs=[c.path("derived", "cosore_annual.csv")])
try:
    RC.repro_checks(c); print("returned")
except Exception as e:
    print("RAISED", type(e).__name__, str(e)[:100])
for r in read_json(c.path("results", "reproduction_check.json"))["rows"][:3]:
    print(" ", r["status"], "|", r["quantity"], "|", r["v3"], "|", r.get("diff"), "|", r["note"][:80])
print(" summary", read_json(c.path("results", "reproduction_check.json"))["summary"])
