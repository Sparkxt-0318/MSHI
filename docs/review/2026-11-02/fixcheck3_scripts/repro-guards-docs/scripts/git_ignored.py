"""verify_git_checkout with --ignored=matching on a local repo carrying the COSORE v0.8.0 .gitignore rules
(copied from the scratch copy of the pinned checkout). Uses the real git_checkout_commit (file:// origin)."""
import shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi import netutil as N

W = Path(sys.argv[1]); SRC = Path(sys.argv[2])     # SRC: scratch copy of the COSORE checkout (for .gitignore texts)
shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
env = {**N.GIT_ENV, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}
def g(*a, cwd): return subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout
origin = W / "origin"; origin.mkdir()
for rel in [".gitignore", "inst/extdata/.gitignore", "inst/extdata/datasets/d20200228_RENCHON/data/.gitignore",
            "gcb/.gitignore", "vignettes/.gitignore", ".github/.gitignore"]:
    (origin / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(SRC / rel, origin / rel)
for ds in ["dA", "d20200228_RENCHON"]:
    (origin / "inst/extdata/datasets" / ds).mkdir(parents=True, exist_ok=True)
    (origin / "inst/extdata/datasets" / ds / "DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\n")
(origin / "cosore.Rproj").write_text("Version: 1.0\n")
g("init", "-q", cwd=origin); g("add", "-A", cwd=origin); g("commit", "-q", "--no-gpg-sign", "-m", "c", cwd=origin)
commit = g("rev-parse", "HEAD", cwd=origin).strip()

def case(label, make):
    dest = W / ("co_" + label.replace(" ", "_").replace("/", "_"))
    N.git_checkout_commit(f"file://{origin}", commit, dest)       # fresh, clean checkout
    make(dest)
    st = subprocess.run(["git", "-C", str(dest), "--no-optional-locks", "status", "--porcelain", "--untracked-files=all",
                         "--ignored=matching"], env=N.GIT_ENV, capture_output=True, text=True).stdout.split("\n")[:3]
    try:
        N.verify_git_checkout(dest, commit); out = "ACCEPTED"
    except Exception as e:
        out = f"REFUSED ({type(e).__name__})"
    # the idempotent fetch path (what fetch_cosore runs on every `make all`)
    try:
        N.git_checkout_commit(f"file://{origin}", commit, dest); out2 = "fetch ok"
    except Exception as e:
        out2 = f"fetch {type(e).__name__}"
    print(f"{label:45s} {out:35s} {out2:35s} status: {[s for s in st if s]}")

def w(rel, text="x"):
    def f(dest):
        p = dest / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    return f
case("clean", lambda d: None)
case("untracked dataset dB (control)", w("inst/extdata/datasets/dB/DESCRIPTION.txt"))
case("dataset named doc", w("inst/extdata/datasets/doc/data/data.RDS"))
case("dataset named Meta", w("inst/extdata/datasets/Meta/DESCRIPTION.txt"))
case("RENCHON data.RDS (embargoed, *.RDS)", w("inst/extdata/datasets/d20200228_RENCHON/data/data.RDS"))
case("macOS .DS_Store at top level", w(".DS_Store"))
case("macOS .DS_Store inside datasets/dA", w("inst/extdata/datasets/dA/.DS_Store"))
case("RStudio .Rproj.user/ (opened cosore.Rproj)", w(".Rproj.user/shared/notebooks/x"))
case("R session .Rhistory", w(".Rhistory"))
case("built vignette vignettes/x.html", w("vignettes/x.html"))
