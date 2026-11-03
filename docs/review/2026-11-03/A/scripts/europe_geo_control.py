"""europe_geo_sensitivity's guards, in a copy of the 'chain' sandbox's features: (1) features table changed on disk
after features.json recorded it -> refused (stale); (2) features re-recorded with one Asia training site's bio01
changed -> the control (full locked Europe set vs the locked metrics) fails and nothing is written; (3) the stage
writes only results/europe_geo_sensitivity.json and leaves the locked files' bytes unchanged."""
import hashlib, json, shutil, sys
from pathlib import Path
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/scripts")
import numpy as np, pandas as pd
import chain_cfg as C
cfg = C.make_cfg()
from mshi.io import StaleInputError, write_result, write_table, require_current, _read_result
from mshi.analysis import clean_test as CT, europe_geo as EG
REPO = Path("/home/user/MSHI")
locked_files = [REPO / "docs/handoff/results/clean_test_europe.json", REPO / "docs/handoff/results/clean_test_europe_repo_sensitivity.json",
                REPO / "docs/handoff/ANALYSIS_PLAN_LOCKED.md"]
h0 = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in locked_files}
fp = cfg.path("interim", "features_v3_qc.parquet")
bak = {p: p.read_bytes() for p in [fp, cfg.path("interim", "features_v3_repo.parquet"), cfg.path("results", "features.json"),
                                   cfg.path("results", "europe_geo_sensitivity.json")]}
d = pd.read_parquet(fp)
lt = CT.LockedTest(cfg)
a, e, _f, _m, p = lt.score(d[d.continent == "Asia"], d[d.continent == "Europe"], "TP", "OLS-TP")
fake = {"selected": {"set": "TP", "learner": "OLS-TP"},
        "primary": lt.metrics(e.log_rs.values, p, e.lon.values, e.lat.values, np.full(len(e), a.log_rs.mean()))}
real = EG.read_json
EG.read_json = lambda path: fake if "clean_test_europe" in str(path) else real(path)
try:
    out = EG.europe_geo_sensitivity(cfg)
    print("(0) unchanged features: control passes, n =", out["n"])
    d2 = d.copy(); i = d2.index[d2.continent == "Asia"][0]; d2.loc[i, "bio01"] += 1.0
    write_table(d2, fp)
    try:
        EG.europe_geo_sensitivity(cfg); print("(1) NOT refused")
    except StaleInputError as ex:
        print("(1) table changed after features.json recorded it -> refused:", str(ex)[:110])
    cfg.reads.pop("features.json", None)
    b, _ = _read_result(cfg, "features.json")
    write_result(cfg, b, "features.json", outputs=[fp, cfg.path("interim", "features_v3_repo.parquet")])
    res = cfg.path("results", "europe_geo_sensitivity.json"); res.unlink()
    try:
        EG.europe_geo_sensitivity(cfg); print("(2) control did NOT fail")
    except EG.ControlMismatch as ex:
        print("(2) re-recorded features with one Asia bio01 changed -> ControlMismatch:", str(ex)[:100],
              "; result written:", res.exists())
finally:
    for pth, bts in bak.items():
        pth.write_bytes(bts)
h1 = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in locked_files}
print("(3) locked plan and locked results unchanged:", h0 == h1)
