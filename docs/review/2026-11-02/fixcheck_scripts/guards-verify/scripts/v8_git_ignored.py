"""Claim 8: verify_git_checkout's clean-worktree check ignores gitignored files.

A scratch origin carries the SAME .gitignore files as the pinned COSORE commit (read from the real checkout's
object store with `git show`, read-only). The real mshi.netutil.git_checkout_commit / verify_git_checkout are used
on a scratch checkout; cosore_annual's dataset loop (cosore.py:94) is evaluated on it.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcommon import REPO, WORK, Path  # noqa: E402

from mshi.netutil import ChecksumMismatchError, git_checkout_commit, verify_git_checkout  # noqa: E402

REAL = Path(REPO) / "data" / "raw" / "cosore" / "02f32e8e"
ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
IGN = [".gitignore", "inst/extdata/.gitignore", "inst/extdata/datasets/d20200228_RENCHON/data/.gitignore"]


def git(*a, cwd):
    return subprocess.run(["git", "-c", "user.email=v@example.invalid", "-c", "user.name=v", *a], cwd=cwd,
                          capture_output=True, text=True, env=ENV, check=True).stdout


W = WORK / "v8"; shutil.rmtree(W, ignore_errors=True)
src = W / "origin"; src.mkdir(parents=True)
git("init", "-q", cwd=src)
git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=src)
for rel in IGN:
    txt = subprocess.run(["git", "--no-optional-locks", "show", f"HEAD:{rel}"], cwd=REAL, capture_output=True,
                         text=True, env=ENV, check=True).stdout
    (src / rel).parent.mkdir(parents=True, exist_ok=True)
    (src / rel).write_text(txt)
ds = src / "inst/extdata/datasets"
(ds / "dA" / "data").mkdir(parents=True)
(ds / "dA" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\nCSR_LONGITUDE: 2\n")
(ds / "dA" / "data" / "data.RDS").write_bytes(b"\x1f\x8b fake")
(ds / "d20200228_RENCHON" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 3\nCSR_LONGITUDE: 4\n")
git("add", "-A", cwd=src)
git("commit", "-qm", "c1", cwd=src)
commit = git("rev-parse", "HEAD", cwd=src).strip()

dest = W / "co"
print("first checkout:", {k: v for k, v in git_checkout_commit(f"file://{src}", commit, dest).items() if k != "path"})
root = dest / "inst/extdata/datasets"


def attempt(label):
    try:
        verify_git_checkout(dest, commit)
        verdict = "ACCEPTED as clean"
    except ChecksumMismatchError as e:
        verdict = "refused: " + str(e).split("local changes")[1][:80]
    loop = [d.name for d in sorted(d for d in root.iterdir() if d.is_dir())]      # cosore.py:94
    print(f"  {label:58s} -> {verdict}; cosore_annual dataset loop = {loop}")


attempt("pristine checkout")
(root / "dB").mkdir(); (root / "dB" / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 5\nCSR_LONGITUDE: 6\n")
attempt("control: new dataset dir 'dB' (untracked)")
shutil.rmtree(root / "dB")
for name in ("doc", "Meta"):
    (root / name / "data").mkdir(parents=True)
    (root / name / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 7\nCSR_LONGITUDE: 8\n")
    (root / name / "data" / "data.RDS").write_bytes(b"\x1f\x8b fake")
    attempt(f"new dataset dir '{name}' with DESCRIPTION.txt + data/data.RDS")
    shutil.rmtree(root / name)
(root / "d20200228_RENCHON" / "data").mkdir(parents=True, exist_ok=True)
(root / "d20200228_RENCHON" / "data" / "data.RDS").write_bytes(b"\x1f\x8b embargoed data")
attempt("data/data.RDS added to the embargoed RENCHON dataset")
print("  git status --porcelain --untracked-files=all          :",
      git("--no-optional-locks", "status", "--porcelain", "--untracked-files=all", cwd=dest).split())
print("  git status --porcelain --untracked-files=all --ignored:",
      git("--no-optional-locks", "status", "--porcelain", "--untracked-files=all", "--ignored", cwd=dest).split())
