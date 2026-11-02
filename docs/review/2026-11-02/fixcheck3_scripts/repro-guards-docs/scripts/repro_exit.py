"""run(['repro_checks']) exit codes and run-log statuses in a NON-smoke sandbox (absolute scratch paths)."""
import copy, json, shutil, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
from mshi.io import write_result, read_json
from mshi.run import run
from mshi.analysis.clean_test import compare_with_locked

REPO = Path("/home/user/MSHI"); W = Path(sys.argv[1]); BASE = load_config()

def full(name, seed=None):
    sb = W / name; shutil.rmtree(sb, ignore_errors=True)
    d = copy.deepcopy(BASE.data)
    for root in ("interim", "derived", "results", "figures"):
        d["paths"][root] = str(sb / d["paths"][root])
    if seed is not None: d["smoke"]["seed"] = seed
    cfg = Config(d, source=BASE.source)
    shutil.copytree(REPO / "data" / "derived", cfg.path("derived"))
    cfg.path("results").mkdir(parents=True)
    for name_, outs in [("cosore_annual.json", ["cosore_annual.csv"]),
                        ("build_sites.json", ["records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet"])]:
        obj = read_json(REPO / "results" / name_)
        write_result(cfg, obj, name_, outputs=[cfg.path("derived", o) for o in outs])
    return cfg

def rerun(cfg, tag, mutate=None, write_cfg=None):
    lr = cfg["clean_test"]["locked_results"][tag]
    R = read_json(cfg.repo_path(lr["file"]))
    if mutate: mutate(R)
    R["vs_locked"] = compare_with_locked(R, read_json(cfg.repo_path(lr["file"])), cfg["clean_test"]["deviation_atol"])
    write_result(write_cfg or cfg, R, f"clean_test_rerun_{tag}.json")

def case(name, cfg):
    code = run(["repro_checks"], cfg)
    last = [json.loads(l) for l in cfg.path("results", "run_log.jsonl").read_text().splitlines()][-1]
    s = read_json(cfg.path("results", "reproduction_check.json"))["summary"]
    print(f"{name}: exit {code}; run_log repro_checks status {last['status'][:110]!r}; summary {s}")

other = lambda cfg: Config(dict(cfg.data, smoke={**cfg["smoke"], "seed": 1}), source=cfg.source)
c = full("E0"); case("E0 committed state (NOT RUN rows only)", c)
c = full("E1"); rerun(c, "qc"); rerun(c, "repo"); case("E1 both identical", c)
c = full("E2"); rerun(c, "qc"); rerun(c, "repo", lambda R: R["primary"].__setitem__("r2", R["primary"]["r2"] - 0.01)); case("E2 repo DEVIATION", c)
c = full("E3"); rerun(c, "qc"); rerun(c, "repo", write_cfg=other(c)); case("E3 repo STALE", c)
c = full("E4"); rerun(c, "qc", lambda R: R["primary"].__setitem__("n", 236)); rerun(c, "repo", write_cfg=other(c)); case("E4 FAIL (Europe n 236) + STALE", c)
