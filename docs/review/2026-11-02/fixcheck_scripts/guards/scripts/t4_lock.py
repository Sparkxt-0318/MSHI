import copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import yaml, logging
logging.basicConfig(level=logging.CRITICAL)
from mshi.config import canonical_sha256, load_config
from mshi.analysis import clean_test as CT
from mshi.run import main

W = Path(SCR) / "work" / "t4"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
base = load_config()

def alt(name, edit, rehash=True):
    d = copy.deepcopy(base.data)
    for k in ("interim", "derived", "results", "figures"):
        d["paths"][k] = str(W / name / k)
    d["paths"]["raw"] = str(W / name / "raw")
    edit(d)
    if rehash:
        d["clean_test"]["locked_sha256"] = canonical_sha256(d["clean_test"]["locked"])
    p = W / f"{name}.yaml"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    return p

cases = {
    "test_NA": lambda d: d["clean_test"]["locked"].__setitem__("test_continent", "North America"),
    "tie_0.05": lambda d: d["clean_test"]["locked"].__setitem__("tie_margin", 0.05),
    "C8+NPP_no_npp": lambda d: d["clean_test"]["locked"]["sets"]["C8+NPP"].remove("npp"),
    "rf_predict_2": lambda d: d["clean_test"]["locked"]["rf"].__setitem__("predict_n_jobs", 2),
    "anchors_too": lambda d: (d["clean_test"]["locked"].__setitem__("bootstrap_n", 200)),
    "plan_sha_field": lambda d: d["clean_test"].__setitem__("plan_sha256", "0" * 64),
    "locked_result_sha_field": lambda d: d["clean_test"]["locked_results"]["qc"].__setitem__("sha256", "0" * 64),
}
for name, ed in cases.items():
    p = alt(name, ed)
    cfg = load_config(p)
    try:
        CT.verify_lock(cfg); v = "PASSES"
    except CT.LockedPlanError as e:
        v = "refused" + (" (message contains new hash!)" if canonical_sha256(cfg["clean_test"]["locked"]) in str(e) else "")
    code = main(["--config", str(p), "--stage", "clean_test"])
    written = sorted(str(x.relative_to(W / name)) for x in (W / name).rglob("*") if x.is_file())
    print(f"{name:24s} verify_lock: {v:8s} | main exit {code} | files written: {written}")

# key order of `sets` is not part of the canonical hash (sort_keys) but is the candidate order
def reorder(d):
    s = d["clean_test"]["locked"]["sets"]
    d["clean_test"]["locked"]["sets"] = {k: s[k] for k in ["ALL", "C8+SOIL", "C8+MODIS", "C8+NPP", "C8"]}
p = alt("reordered_sets", reorder, rehash=False)
cfg = load_config(p)
info = CT.verify_lock(cfg)
lt = CT.LockedTest(cfg)
print("reordered sets: verify_lock passes:", info["locked_sha256"] == CT.LOCKED_SHA256,
      "| candidate order:", [f"{s}/{l}" for s, l in lt.cands][:4], "... vs default",
      [f"{s}/{l}" for s, l in CT.LockedTest(base).cands][:4])
# A config that leaves the locked block alone but changes the site build passes the lock (covered instead by provenance)
p = alt("site_build_edit", lambda d: d["site_build"]["continent"].__setitem__("russia_split_lon", 40.0), rehash=False)
print("site_build edit: verify_lock passes:", CT.verify_lock(load_config(p))["locked_sha256"] == CT.LOCKED_SHA256,
      "| config_sha256 differs from default:", load_config(p).sha256() != base.sha256())
# require_lock=False use outside tests?
import subprocess
print(subprocess.run(["grep", "-rn", "require_lock", REPO + "/mshi", REPO + "/tests", "--include=*.py"],
                     capture_output=True, text=True).stdout)
