"""Claim 2: verify_git_checkout (a6c00bc) refuses harmless gitignored files (.DS_Store, .Rproj.user, .Rhistory).

Run: GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 /home/user/MSHI/.venv/bin/python -I -B c2_cosore_ignored.py V
V/c2/raw/cosore/02f32e8e is a `cp -a` copy of the real checkout (the real one is never touched).
"""
import copy
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

V = Path(sys.argv[1])
sys.path.insert(0, "/home/user/MSHI")

import requests  # noqa: E402


def guard(self, request, **kw):
    raise requests.exceptions.ConnectionError(f"verify network guard: refused {request.url}")


requests.sessions.Session.send = guard

from mshi.config import load_config, Config  # noqa: E402
from mshi import netutil  # noqa: E402

COMMIT = "02f32e8e7f9a0f1c26c9dad61c574aef863f1df1"
CO = V / "c2" / "raw" / "cosore" / "02f32e8e"
DS = CO / "inst" / "extdata" / "datasets"


def old_verify():
    """pre-a6c00bc verify_git_checkout (git archive 9e17a36), loaded from scratch."""
    # old netutil does `from .io import sha256_file`; give it the current io (sha256_file unchanged)
    src = (V / "old9e" / "mshi" / "netutil.py").read_text().replace("from .io import sha256_file",
                                                                     "from mshi.io import sha256_file")
    mod = type(sys)("old_netutil")
    exec(compile(src, "old9e/mshi/netutil.py", "exec"), mod.__dict__)
    return mod.verify_git_checkout


OLD = old_verify()


def check(label):
    out = {"label": label}
    for name, fn in (("a6c00bc", netutil.verify_git_checkout), ("9e17a36", OLD)):
        try:
            r = fn(CO, COMMIT)
            out[name] = f"accepted (tree {r['tree'][:12]})"
        except Exception as e:  # noqa: BLE001
            out[name] = f"{type(e).__name__}: {str(e)[-200:]}"
    st = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(CO), "--no-optional-locks", "check-ignore",
                         "-v", "--no-index", "inst/extdata/datasets/.DS_Store", ".Rproj.user/x", ".Rhistory"],
                        capture_output=True, text=True)
    out["check_ignore"] = st.stdout.strip().splitlines()
    # what cosore_annual iterates (cosore.py:93): directories directly under datasets_dir
    out["n_dataset_dirs_cosore_annual_sees"] = len([d for d in DS.iterdir() if d.is_dir()])
    print(json.dumps(out, indent=1))
    return out


log = {"clean": check("clean copy")}
first_ds = sorted(d for d in DS.iterdir() if d.is_dir())[0]

# 1. Finder-style .DS_Store in the datasets dir
(DS / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1" + b"\x00" * 64)
log["ds_store_datasets"] = check("inst/extdata/datasets/.DS_Store")
(DS / ".DS_Store").unlink()

# 2. .DS_Store inside one dataset directory
(first_ds / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1" + b"\x00" * 64)
log["ds_store_in_dataset"] = check(f"{first_ds.name}/.DS_Store")
(first_ds / ".DS_Store").unlink()

# 3. RStudio project state at the checkout root (opening cosore.Rproj creates .Rproj.user/)
(CO / ".Rproj.user" / "shared").mkdir(parents=True)
(CO / ".Rproj.user" / "shared" / "notebooks").write_text("x")
(CO / ".Rhistory").write_text("library(cosore)\n")
log["rstudio"] = check(".Rproj.user/ + .Rhistory")
shutil.rmtree(CO / ".Rproj.user")
(CO / ".Rhistory").unlink()

# 4. control: an untracked (not ignored) file is refused by both versions
(DS / "notes.txt").write_text("x")
log["untracked_control"] = check("untracked notes.txt (control)")
(DS / "notes.txt").unlink()

log["clean_again"] = check("clean again")

# 5. the pipeline: fetch_cosore + cosore_annual via mshi.run.run, non-smoke sandbox, with .DS_Store present
(DS / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1" + b"\x00" * 64)
base = load_config()
data = copy.deepcopy(base.data)
sb = V / "c2" / "sb"
for root in ("interim", "derived", "results", "figures"):
    data["paths"][root] = str(sb / root)
data["paths"]["raw"] = str(V / "c2" / "raw")
cfg = Config(data, source=base.source)        # out_root None: not a smoke run
import mshi.run as R  # noqa: E402
code = R.run(["fetch_cosore", "cosore_annual", "build_sites"], cfg)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
log["pipeline"] = {"exit": code, "stages": [(r["stage"], r["status"][:260]) for r in recs[-3:]]}
cfg2 = Config(copy.deepcopy(data), source=base.source)
code2 = R.run(["cosore_annual"], cfg2)
recs = [json.loads(x) for x in cfg.path("results", "run_log.jsonl").read_text().splitlines()]
log["pipeline_cosore_annual_alone"] = {"exit": code2, "stages": [(r["stage"], r["status"][:260]) for r in recs[-1:]]}
(DS / ".DS_Store").unlink()
print(json.dumps({k: log[k] for k in ("pipeline", "pipeline_cosore_annual_alone")}, indent=1))
(V / "logs" / "c2_cosore_ignored.json").write_text(json.dumps(log, indent=1))
