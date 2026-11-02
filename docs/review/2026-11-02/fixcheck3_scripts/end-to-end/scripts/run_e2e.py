"""Driver: python -I -B run_e2e.py setup SB | run SB LABEL CONFIG_YAML

setup: builds SB/raw (copies of the pinned SRDB + Natural Earth files, a read-only symlink to the COSORE checkout)
       and writes SB/configs/{base,q05,unrelated}.yaml (absolute scratch paths, NOT a smoke run).
run:   installs the fakes (e2e_lib) and calls mshi.run.main(["--stage", "all", "--config", CONFIG_YAML]),
       exactly what `python -m mshi.run --stage all` does; writes SB/../logs/LABEL.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import copy  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402

import yaml  # noqa: E402

import e2e_lib as E  # noqa: E402

REPO = Path("/home/user/MSHI")


def setup(sb: Path):
    raw = sb / "raw"
    (raw / "srdb" / "02163a72").mkdir(parents=True, exist_ok=True)
    for f in ("srdb-data.csv", "LICENSE"):
        shutil.copy2(REPO / "data/raw/srdb/02163a72" / f, raw / "srdb" / "02163a72" / f)
    (raw / "naturalearth" / "v5.1.2").mkdir(parents=True, exist_ok=True)
    for f in ("ne_50m_admin_0_countries.geojson", "ne_110m_land.geojson", "ne_50m_land.geojson"):
        shutil.copy2(REPO / "data/raw/naturalearth/v5.1.2" / f, raw / "naturalearth" / "v5.1.2" / f)
    if not (raw / "cosore").exists():
        (raw / "cosore").symlink_to(REPO / "data/raw/cosore", target_is_directory=True)
    cdir = sb / "configs"
    cdir.mkdir(parents=True, exist_ok=True)
    base = E.make_cfg(sb).data
    variants = {"base": base}
    q = copy.deepcopy(base)
    q["sources"]["soilgrids"]["statistic"] = "Q0.5"
    variants["q05"] = q
    u = copy.deepcopy(base)
    u["smoke"]["seed"] = 1                         # unrelated to every full-run number
    variants["unrelated"] = u
    for k, d in variants.items():
        (cdir / f"{k}.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    print("setup ok", sorted(p.name for p in cdir.iterdir()))


def run(sb: Path, label: str, cfg_yaml: Path, stages=("all",)):
    from mshi.config import load_config
    E.install()
    E.reset_state()
    import mshi.run as R
    argv = []
    for s in stages:
        argv += ["--stage", s]
    argv += ["--config", str(cfg_yaml)]
    cfg = load_config(cfg_yaml)
    n_before = len(cfg.path("results", "run_log.jsonl").read_text().splitlines()) \
        if cfg.path("results", "run_log.jsonl").exists() else 0
    before = E.tree_hashes(cfg.path("results")) if cfg.path("results").exists() else {}
    t0 = time.time()
    code = R.main(argv)
    secs = round(time.time() - t0, 1)
    recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()][n_before:]
    after = E.tree_hashes(cfg.path("results"))
    out = {
        "label": label, "config": str(cfg_yaml), "exit_code": code, "seconds": secs,
        "stages": [(r["stage"], r["status"][:300], r["seconds"], (r.get("result") or {}).get("cached")
                    if isinstance(r.get("result"), dict) else None) for r in recs],
        "state": {k: (v if not isinstance(v, list) or len(v) < 60 else {"n": len(v), "first": v[:10]})
                  for k, v in E.STATE.items()},
        "staleness_after": E.staleness_report(cfg),
        "results_changed": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
        "results_hashes": after,
        "derived_hashes": E.tree_hashes(cfg.path("derived")),
        "interim_hashes": E.tree_hashes(cfg.path("interim")) if cfg.path("interim").exists() else {},
        "raw_hashes": {k: v for k, v in E.tree_hashes(cfg.path("raw")).items()
                       if not k.startswith(("cosore",))},
    }
    rc = cfg.path("results", "reproduction_check.json")
    if rc.exists():
        j = json.loads(rc.read_text())
        out["repro_summary"] = j["summary"]
        out["repro_rows"] = [(r["quantity"], r["status"], r.get("v3"), r.get("note", "")[:160]) for r in j["rows"]]
    logs = sb.parent / "logs"
    logs.mkdir(exist_ok=True)
    (logs / f"{label}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("label", "exit_code", "seconds", "stages", "state",
                                           "staleness_after", "results_changed")}, indent=1, default=str))
    if "repro_summary" in out:
        print("SUMMARY", out["repro_summary"])
        for row in out["repro_rows"]:
            print("ROW", row)
    return code


if __name__ == "__main__":
    cmd = sys.argv[1]
    sb = Path(sys.argv[2]).resolve()
    if cmd == "setup":
        setup(sb)
    elif cmd == "run":
        stages = tuple(sys.argv[5:]) or ("all",)
        sys.exit(0 if run(sb, sys.argv[3], Path(sys.argv[4]), stages) is not None else 3)
