"""clean_test.deviation_atol: a config edit turns a DEVIATION into PASS and no test fails.
Re-run JSONs are copies of the locked results with a synthetic shift (nothing is scored)."""
import copy, shutil, sys
from pathlib import Path
REPO = Path(sys.argv[1]); W = Path(sys.argv[2])          # REPO: scratch copy of the repository
sys.path[:0] = [str(REPO), str(REPO / "tests")]
import pytest
from mshi.config import Config, load_config
from mshi.io import write_result, read_json
from mshi.analysis import repro_checks as RC
from mshi.analysis.clean_test import compare_with_locked
import test_guards as TG, test_regression as TR

base = load_config()
def run_case(atol):
    sb = W / f"atol_{atol:g}"; shutil.rmtree(sb, ignore_errors=True); (sb / "results").mkdir(parents=True)
    shutil.copytree(REPO / "data" / "derived", sb / "data" / "derived")
    d = copy.deepcopy(base.data); d["clean_test"]["deviation_atol"] = atol
    cfg = Config(d, source=base.source, out_root=sb)
    for name, outs in [("cosore_annual.json", ["cosore_annual.csv"]),
                       ("build_sites.json", ["records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet"])]:
        write_result(cfg, read_json(REPO / "results" / name), name, outputs=[cfg.path("derived", o) for o in outs])
    for tag in ["qc", "repo"]:
        lr = cfg["clean_test"]["locked_results"][tag]
        locked = read_json(cfg.repo_path(lr["file"]))
        R = copy.deepcopy(locked)
        if tag == "qc":                                    # a re-run whose Europe R2 moved by 0.004 (within +-0.01)
            R["primary"]["r2"] += 0.004
        R["vs_locked"] = compare_with_locked(R, locked, cfg["clean_test"]["deviation_atol"])
        R["lock"] = {"locked_sha256": cfg["clean_test"]["locked_sha256"]}
        write_result(cfg, R, f"clean_test_rerun_{tag}.json")
    s = RC.repro_checks(cfg)
    row = [r for r in read_json(cfg.path("results", "reproduction_check.json"))["rows"]
           if r["quantity"] == "Locked test: re-run identical to the locked result"][0]
    outcomes = {}
    for fn, args in [(TG.test_reproduction_targets_are_the_briefs, (cfg,)), (TG.test_lock_ok_on_repo, (cfg,)),
                     (TG.test_config_hashes_equal_code_anchors, (cfg,)),
                     (TR.test_locked_rerun_reported_against_locked_result, (cfg, "qc")),
                     (TR.test_locked_test_rerun, (cfg,)), (TR.test_reproduction_table_has_no_fail, (cfg,))]:
        try:
            fn(*args); outcomes[fn.__name__] = "pass"
        except BaseException as e:
            outcomes[fn.__name__] = f"FAIL ({type(e).__name__})"
    print(f"deviation_atol={atol:g}: row {row['status']} v3={row['v3']!r}; summary {s}")
    print("   tests:", outcomes)
run_case(1e-9)
run_case(0.05)
