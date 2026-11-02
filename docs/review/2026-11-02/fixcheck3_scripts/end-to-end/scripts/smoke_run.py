"""Smoke run (`make smoke` equivalent) in a scratch sandbox: relative output paths under out_root, raw in scratch."""
import sys
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, sys.argv[1] + "/scripts")
import copy, json, logging
from pathlib import Path
import e2e_lib as E
from mshi.config import Config, load_config
from mshi.run import _stages, run
logging.basicConfig(level=logging.WARNING)
E.install()
base = load_config()
data = copy.deepcopy(base.data)
data["paths"]["raw"] = str(Path(sys.argv[2]) / "raw")
cfg = Config(data, source=base.source, out_root=Path(sys.argv[2]) / "out")
for k in range(2):
    E.reset_state()
    code = run([s.name for s in _stages()], cfg, full=True)
    recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-13:]
    print("smoke run", k + 1, "exit", code, [(r["stage"], r["status"][:120], (r.get("result") or {}).get("cached") if isinstance(r.get("result"), dict) else None) for r in recs])
    print("  state", {kk: (v if not isinstance(v, list) else len(v)) for kk, v in E.STATE.items()})
    print("  staleness", E.staleness_report(cfg))
    print("  results hashes", {p.name: E.tree_hashes(cfg.path("results")).get(p.name, "")[:10] for p in E.result_files(cfg)})
