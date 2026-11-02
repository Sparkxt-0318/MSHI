"""Common helpers for the chain re-check (scratch only; the repository is read-only)."""
import copy, json, os, shutil, sys
from pathlib import Path
REPO = Path("/home/user/MSHI")
SCR = Path("fixcheck3_scripts/chain")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from mshi.config import Config, load_config  # noqa: E402

CFG = load_config()


def full_sand(name, edit=None, base=None) -> Config:
    """Non-smoke sandbox (out_root None): every output root an absolute scratch path."""
    root = (base or SCR / "work") / name
    data = copy.deepcopy(CFG.data)
    for r in ("raw", "interim", "derived", "results", "figures"):
        data["paths"][r] = str(root / r)
    if edit:
        edit(data)
    return Config(data, source=CFG.source)


def smoke_sand(name, edit=None) -> Config:
    data = copy.deepcopy(CFG.data)
    if edit:
        edit(data)
    return Config(data, source=CFG.source, out_root=SCR / "work" / name)


def reset(path):
    shutil.rmtree(path, ignore_errors=True)
    Path(path).mkdir(parents=True, exist_ok=True)


def link_raw(sand):
    """Symlink the pinned SRDB, Natural Earth and COSORE inputs into the sandbox raw root (read only)."""
    from mshi.data.fetch import cosore_repo_path, naturalearth_path, srdb_csv_path
    pairs = [(srdb_csv_path(CFG), srdb_csv_path(sand)), (srdb_csv_path(CFG).with_name("LICENSE"), srdb_csv_path(sand).with_name("LICENSE")),
             (cosore_repo_path(CFG), cosore_repo_path(sand))]
    for f in CFG["sources"]["naturalearth"]["files"]:
        pairs.append((naturalearth_path(CFG, f), naturalearth_path(sand, f)))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            os.symlink(src, dst)


def stub_git():
    """Never run git inside data/raw (the COSORE checkout is downloaded data)."""
    import mshi.netutil as N
    N.verify_git_checkout = lambda dest, commit: {"commit": commit, "tree": "stub"}


def committed(name):
    d = json.loads((REPO / "results" / name).read_text())
    d.pop("_provenance", None)
    d.pop("_outputs", None)
    return d


def seed_committed(sand, names=("cosore_annual.json", "build_sites.json"), files=None):
    """Copy committed derived tables into the sandbox and re-stamp the committed results under the sandbox
    config, with their outputs (stands in for the committed state produced under this config)."""
    from mshi.io import write_result
    outs = {"cosore_annual.json": ["cosore_annual.csv"],
            "build_sites.json": ["sites_v3_qc.parquet", "sites_v3_repo.parquet", "records_v3.parquet"]}
    for n in names:
        ps = []
        for f in outs.get(n, []):
            dst = sand.path("derived", f)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / "data" / "derived" / f, dst)
            ps.append(dst)
        write_result(sand, committed(n), n, outputs=ps)


def runlog(sand):
    p = sand.path("results", "run_log.jsonl")
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def statuses(sand, since=0):
    return {r["stage"]: r["status"][:150] for r in runlog(sand)[since:]}


def summary(sand):
    p = sand.path("results", "reproduction_check.json")
    return json.loads(p.read_text())["summary"] if p.exists() else None


def rows(sand):
    return json.loads(sand.path("results", "reproduction_check.json").read_text())["rows"]
