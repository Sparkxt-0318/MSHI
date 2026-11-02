"""Claim 1 driver: python -I -B c1_driver.py V setup SB | V run SB LABEL STAGE [STAGE ...]

setup: SB/raw with copies of the pinned SRDB + Natural Earth files and a symlink to V/c2/raw/cosore (my cp -a copy
       of the COSORE checkout); SB/configs/base.yaml = configs/v3.yaml with absolute SB paths (NOT a smoke run).
run:   installs c1_fakes and calls mshi.run.main(["--stage", S, ..., "--config", SB/configs/base.yaml]), which is what
       the Makefile targets do; writes V/logs/c1_LABEL.json.
"""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

V = Path(sys.argv[1])
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, str(V / "scripts"))

import yaml  # noqa: E402

REPO = Path("/home/user/MSHI")


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()} if root.exists() else {}


def setup(sb: Path):
    raw = sb / "raw"
    (raw / "srdb" / "02163a72").mkdir(parents=True, exist_ok=True)
    for f in ("srdb-data.csv", "LICENSE"):
        shutil.copy2(REPO / "data/raw/srdb/02163a72" / f, raw / "srdb/02163a72" / f)
    (raw / "naturalearth" / "v5.1.2").mkdir(parents=True, exist_ok=True)
    for f in ("ne_50m_admin_0_countries.geojson", "ne_110m_land.geojson", "ne_50m_land.geojson"):
        shutil.copy2(REPO / "data/raw/naturalearth/v5.1.2" / f, raw / "naturalearth/v5.1.2" / f)
    if not (raw / "cosore").exists():
        (raw / "cosore").symlink_to(V / "c2" / "raw" / "cosore", target_is_directory=True)
    d = yaml.safe_load((REPO / "configs/v3.yaml").read_text())
    for r in ("raw", "interim", "derived", "results", "figures"):
        d["paths"][r] = str(sb / r)
    (sb / "configs").mkdir(parents=True, exist_ok=True)
    (sb / "configs" / "base.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    print("setup ok")


def run(sb: Path, label: str, stages: list[str]):
    import c1_fakes as F
    F.install()
    import mshi.run as R
    from mshi.config import load_config
    from mshi.io import result_staleness
    cy = sb / "configs" / "base.yaml"
    cfg = load_config(cy)
    lp = cfg.path("results", "run_log.jsonl")
    n0 = len(lp.read_text().splitlines()) if lp.exists() else 0
    argv = sum((["--stage", s] for s in stages), []) + ["--config", str(cy)]
    code = R.main(argv)
    recs = [json.loads(x) for x in lp.read_text().splitlines()][n0:]
    stale = {}
    for p in sorted(cfg.path("results").glob("*.json")):
        j = json.loads(p.read_text())
        stale[p.name] = result_staleness(cfg, j) if "_provenance" in j else "(no provenance)"
    out = {"label": label, "argv": argv, "exit": code, "counts": dict(F.COUNTS),
           "stages": [(r["stage"], r["status"][:220]) for r in recs], "staleness": stale,
           "interim": tree(cfg.path("interim")), "results": tree(cfg.path("results")),
           "raw_worldclim": tree(cfg.path("raw", "worldclim"))}
    fj = cfg.path("results", "features.json")
    if fj.exists():
        out["features_json_outputs"] = {k: v[:16] for k, v in json.loads(fj.read_text()).get("_outputs", {}).items()}
    for t in ("qc", "repo"):
        p = cfg.path("results", f"clean_test_rerun_{t}.json")
        if p.exists():
            j = json.loads(p.read_text())
            out[f"rerun_{t}"] = {"selected": j["selected"], "cv_r2": j["selected"]["cv_r2"],
                                 "r2": j["primary"]["r2"], "ci_site": j["primary"]["ci_site"],
                                 "has_outputs": "_outputs" in j, "keys_with_input_binding":
                                 [k for k in j if k.startswith("_")]}
    rc = cfg.path("results", "reproduction_check.json")
    if rc.exists():
        j = json.loads(rc.read_text())
        out["repro_summary"] = j["summary"]
        out["repro_rows"] = [(r["quantity"], r["status"], r.get("v3"), (r.get("note") or "")[:100])
                             for r in j["rows"] if r["quantity"].startswith("Locked")]
    (V / "logs" / f"c1_{label}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in out if k not in ("interim", "results", "raw_worldclim")}, indent=1,
                     default=str))


if __name__ == "__main__":
    cmd, sb = sys.argv[2], Path(sys.argv[3])
    if cmd == "setup":
        setup(sb)
    else:
        run(sb, sys.argv[4], sys.argv[5:])
