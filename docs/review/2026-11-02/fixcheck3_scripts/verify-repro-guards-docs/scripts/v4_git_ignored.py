"""Claim 4: does verify_git_checkout (--ignored=matching) refuse harmless OS/IDE files in the COSORE checkout?
Local origin in scratch with the six .gitignore files of the pinned COSORE commit (bytes copied from the
real checkout's working tree; nothing is executed from it). Uses the real git_checkout_commit and
verify_git_checkout. Also: what does cosore_annual read, and what did the pre-fix status command print?
Run with python -I -B (reads files under data/raw)."""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")

from mshi.netutil import ChecksumMismatchError, git_checkout_commit, verify_git_checkout  # noqa: E402

SCR = Path("fixcheck3_scripts/verify-repro-guards-docs")
REAL = Path("/home/user/MSHI/data/raw/cosore/02f32e8e")
W = SCR / "work" / "git_ignored"
shutil.rmtree(W, ignore_errors=True)
W.mkdir(parents=True)
ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin", "HOME": str(W)}


def g(*a, cwd):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", "-c", "core.fsmonitor=false", *a],
                          cwd=cwd, env=ENV, capture_output=True, text=True, check=True).stdout


src = W / "src"
src.mkdir()
g("init", "-q", cwd=src)
for gi in [".gitignore", ".github/.gitignore", "gcb/.gitignore", "inst/extdata/.gitignore",
           "inst/extdata/datasets/d20200228_RENCHON/data/.gitignore", "vignettes/.gitignore"]:
    (src / gi).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REAL / gi, src / gi)
for ds in ["dA", "d20200228_RENCHON"]:
    (src / "inst/extdata/datasets" / ds / "data").mkdir(parents=True, exist_ok=True)
    (src / "inst/extdata/datasets" / ds / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\nCSR_LONGITUDE: 2\n")
(src / "inst/extdata/datasets/dA/data/data.RDS").write_bytes(b"not really rds")
(src / "cosore.Rproj").write_text("Version: 1.0\n")
(src / "vignettes/x.Rmd").write_text("vignette\n")
g("add", "-A", cwd=src)
g("commit", "-q", "-m", "c", cwd=src)
commit = g("rev-parse", "HEAD", cwd=src).strip()
origin = W / "origin.git"
g("clone", "-q", "--bare", str(src), str(origin), cwd=W)
g("config", "uploadpack.allowAnySHA1InWant", "true", cwd=origin)

dest = W / "checkout"
info = git_checkout_commit(f"file://{origin}", commit, dest, sleep=lambda s: None)
print("fresh checkout:", {k: info[k] for k in ("commit", "downloaded")})
print("clean checkout verify:", "ok" if verify_git_checkout(dest, commit) else "?")

CASES = {
    ".DS_Store at top level": [".DS_Store"],
    ".DS_Store in datasets/dA": ["inst/extdata/datasets/dA/.DS_Store"],
    ".Rproj.user/ (RStudio project opened)": [".Rproj.user/shared/notebooks/x"],
    ".Rhistory (R session)": [".Rhistory"],
    "vignettes/x.html (built vignette)": ["vignettes/x.html"],
    "control: datasets/doc/DESCRIPTION.txt (the F/R-P1-20 case)": ["inst/extdata/datasets/doc/DESCRIPTION.txt"],
    "control: RENCHON data/data.RDS (embargoed, ignored)": ["inst/extdata/datasets/d20200228_RENCHON/data/data.RDS"],
    "control: untracked dataset dir dB (not ignored)": ["inst/extdata/datasets/dB/DESCRIPTION.txt"],
}
for label, files in CASES.items():
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        (dest / f).write_text("x\n")
    old = subprocess.run(["git", "-C", str(dest), "--no-optional-locks", "status", "--porcelain",
                          "--untracked-files=all"], env=ENV, capture_output=True, text=True).stdout.split("\n")
    old = [x for x in old if x]
    res = []
    for fn, call in [("verify_git_checkout", lambda: verify_git_checkout(dest, commit)),
                     ("git_checkout_commit(idempotent)",
                      lambda: git_checkout_commit(f"file://{origin}", commit, dest, sleep=lambda s: None))]:
        try:
            call()
            res.append(f"{fn}: accepted")
        except ChecksumMismatchError as e:
            res.append(f"{fn}: REFUSED ({str(e).split('local changes ')[1][:60]})")
    print(f"{label:58s} | pre-fix status (no --ignored): {old or 'empty'} | " + " | ".join(res))
    for f in files:                                   # undo
        p = dest / f
        p.unlink()
        top = dest / Path(f).parts[0]
        if top.is_dir() and top.name in (".Rproj.user",):
            shutil.rmtree(top)
        if p.parent.name in ("doc", "dB") and p.parent.is_dir():
            shutil.rmtree(p.parent)

print("\nreal checkout today: git status --ignored=matching prints:",
      repr(subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(REAL), "--no-optional-locks", "status",
                           "--porcelain", "--untracked-files=all", "--ignored=matching"],
                          env=ENV, capture_output=True, text=True).stdout))
