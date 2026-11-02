"""No false STALE when one stage is re-run alone with an unchanged config (real cosore_annual, build_sites,
site_diagnostics), and a second identical run leaves every result byte-identical."""
import sys, json, hashlib, logging
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc
logging.basicConfig(level=logging.WARNING)
cc.stub_git()
from mshi.run import run
from mshi.io import result_staleness, read_json
base = cc.SCR / "work" / "c13"
cc.reset(base)
s = cc.full_sand("s", base=base)
cc.link_raw(s)
cc.seed_committed(s)
def digests():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in sorted(s.path("results").glob("*.json"))}
for stages in (["cosore_annual"], ["build_sites"], ["site_diagnostics"], ["repro_checks"]):
    n = len(cc.runlog(s))
    print(stages, "exit", run(stages, s), cc.statuses(s, n))
print("staleness:", {p.name: result_staleness(s, read_json(p)) for p in sorted(s.path("results").glob("*.json"))})
print("summary:", cc.summary(s))
d1 = digests()
run(["cosore_annual", "build_sites", "site_diagnostics", "repro_checks"], s)
d2 = digests()
print("second run byte-identical results:", d1 == d2, {k: (d1.get(k), d2.get(k)) for k in d2 if d1.get(k) != d2.get(k)})
print("derived outputs equal the committed tables:",
      all((s.path("derived", f).read_bytes() == (cc.REPO / "data/derived" / f).read_bytes())
          for f in ["cosore_annual.csv", "sites_v3_qc.parquet", "sites_v3_repo.parquet", "records_v3.parquet"]))
