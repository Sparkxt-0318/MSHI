import copy, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import yaml, logging
logging.basicConfig(level=logging.CRITICAL)
import mshi.run as R
W = Path(SCR) / "work" / "t10"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
d = copy.deepcopy(load_config().data)
for k in ("interim", "derived", "results", "figures", "raw"):
    d["paths"][k] = str(W / k)
cp = W / "cfg.yaml"; cp.write_text(yaml.safe_dump(d, sort_keys=False))
real = R._stages()
calls = []
def fake(name):
    def f(cfg):
        calls.append(name)
        if name == "modis_points" and os.environ.get("FAIL_MODIS"):
            raise RuntimeError("boom")
        return {"ok": name}
    return f
R._stages = lambda: [R.Stage(s.name, fake(s.name), s.deps, s.doc) for s in real]
for argv in (["--stage", "features", "--stage", "modis_points", "--stage", "build_sites"],
             ["--stage", "repro_checks", "--stage", "clean_test", "--stage", "features", "--stage", "features"]):
    calls.clear()
    code = R.main(["--config", str(cp)] + argv)
    print(argv[1::2], "-> ran", calls, "exit", code, "| environment.json:", (W / "results/environment.json").exists())
os.environ["FAIL_MODIS"] = "1"; calls.clear()
code = R.main(["--config", str(cp), "--stage", "features", "--stage", "modis_points"])
recs = [json.loads(x) for x in (W / "results/run_log.jsonl").read_text().splitlines()][-2:]
print("modis_points errors, features requested after it on the CLI ->", [(r["stage"], r["status"][:45]) for r in recs], "exit", code)
del os.environ["FAIL_MODIS"]; calls.clear()
code = R.main(["--config", str(cp), "--stage", "all"])
print("--stage all ->", len(calls), "stages, exit", code, "| environment.json:", (W / "results/environment.json").exists(),
      "| smoke_subset ran:", "smoke_subset" in calls)
