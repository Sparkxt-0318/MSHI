"""Regenerate site_diagnostics.json, fetch_srdb.json, fetch_naturalearth.json from copies of the raw inputs in
scratch (no network: pinned files present) and compare with the committed results (minus _provenance)."""
import sys, json, copy, shutil
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
from mshi.config import load_config, Config
from mshi.data.fetch import srdb_csv_path, naturalearth_path, fetch_srdb, fetch_naturalearth
from mshi.analysis.site_diagnostics import site_diagnostics
import mshi.netutil as N

S = Path(sys.argv[1]); shutil.rmtree(S, ignore_errors=True)
base = load_config()
d = copy.deepcopy(base.data); d["paths"]["raw"] = str(S / "raw")
c = Config(d, source=base.source, out_root=S / "out")
# copy pinned raw files
src_srdb = srdb_csv_path(base)
dst = srdb_csv_path(c); dst.parent.mkdir(parents=True)
shutil.copy(src_srdb, dst); shutil.copy(src_srdb.with_name("LICENSE"), dst.with_name("LICENSE"))
for f in base["sources"]["naturalearth"]["files"]:
    p = naturalearth_path(c, f); p.parent.mkdir(parents=True, exist_ok=True); shutil.copy(naturalearth_path(base, f), p)
c.path("derived").mkdir(parents=True)
for f in ["records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet"]:
    shutil.copy(base.path("derived", f), c.path("derived", f))
def no_net(*a, **k): raise AssertionError("network attempted")
N.requests.Session.get = no_net
fetch_srdb(c); fetch_naturalearth(c); site_diagnostics(c)
for f in ["fetch_srdb.json", "fetch_naturalearth.json", "site_diagnostics.json"]:
    a = json.loads(c.path("results", f).read_text()); b = json.loads(base.path("results", f).read_text())
    a.pop("_provenance"); b.pop("_provenance")
    print(f, "content identical:", a == b)
