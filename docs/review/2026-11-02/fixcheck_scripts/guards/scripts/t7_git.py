import os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
from mshi.netutil import git_checkout_commit, verify_git_checkout, ChecksumMismatchError, DownloadError, SourceUnavailableError

W = Path(SCR) / "work" / "t7"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
def g(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
src = W / "origin"; (src / "inst/extdata/datasets/dA/data").mkdir(parents=True)
g("init", "-q", cwd=src); g("config", "user.email", "t@example.invalid", cwd=src); g("config", "user.name", "t", cwd=src)
g("config", "uploadpack.allowAnySHA1InWant", "true", cwd=src)
# same ignore rules as the pinned COSORE commit (top-level .gitignore 'Meta'/'doc'; RENCHON data/.gitignore '*.RDS')
(src / ".gitignore").write_text("Meta\ndoc\n.DS_Store\n")
(src / "inst/extdata/datasets/dA/DESCRIPTION.txt").write_text("CSR_LATITUDE: 1\nCSR_LONGITUDE: 2\n")
(src / "inst/extdata/datasets/dA/data/.gitignore").write_text("# embargoed\n*.RDS\ndata.RDS\n")
(src / "inst/extdata/datasets/dA/data/data.RDS").write_bytes(b"tracked-rds")
g("add", "-f", ".", cwd=src); g("commit", "-qm", "c1", cwd=src)
commit = g("rev-parse", "HEAD", cwd=src)
dest = W / "co"
print("first checkout:", git_checkout_commit(f"file://{src}", commit, dest)["downloaded"])
ds = dest / "inst/extdata/datasets"
def check(label):
    try:
        verify_git_checkout(dest, commit); print(f"  {label:70s} -> accepted as clean")
    except ChecksumMismatchError as e:
        print(f"  {label:70s} -> refused ({str(e)[-80:]})")
(ds / "dA/DESCRIPTION.txt").write_text("CSR_LATITUDE: 99\nCSR_LONGITUDE: 2\n"); check("modified DESCRIPTION.txt")
g("checkout", "--", ".", cwd=dest)
(ds / "dA/data/data.RDS").write_bytes(b"replaced"); check("modified tracked data.RDS (matches *.RDS ignore)")
g("checkout", "--", ".", cwd=dest)
(ds / "dA/data/data.RDS").unlink(); check("deleted tracked data.RDS")
g("checkout", "--", ".", cwd=dest)
(ds / "dNEW").mkdir(); (ds / "dNEW/DESCRIPTION.txt").write_text("x"); check("new untracked dataset dir dNEW")
shutil.rmtree(ds / "dNEW")
(ds / "dA/data/diag2.RDS").write_bytes(b"x"); check("new untracked file matching '*.RDS' in dA/data")
(ds / "dA/data/diag2.RDS").unlink()
(ds / "doc/data").mkdir(parents=True); (ds / "doc/DESCRIPTION.txt").write_text("CSR_LATITUDE: 5\nCSR_LONGITUDE: 6\n")
(ds / "doc/data/data.RDS").write_bytes(b"x"); check("new dataset dir named 'doc' (top-level ignore pattern)")
print("  datasets the cosore_annual loop would iterate:", sorted(d.name for d in ds.iterdir() if d.is_dir()))
shutil.rmtree(ds / "doc")
print("  ignore rules at the real pinned COSORE commit (git check-ignore -v):")
real = Path(REPO) / "data/raw/cosore/02f32e8e"
for rel in ["inst/extdata/datasets/doc/DESCRIPTION.txt", "inst/extdata/datasets/Meta/data/data.RDS",
            "inst/extdata/datasets/d20200228_RENCHON/data/extra.RDS",
            "inst/extdata/datasets/d20190526_MINIONS_BNZ/data/data.RDS"]:
    r = subprocess.run(["git", "-C", str(real), "check-ignore", "-v", "--no-index", rel], capture_output=True, text=True,
                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    print(f"    {rel:62s} -> {r.stdout.strip() or 'not ignored'}")

# fetch failure classification
for label, url, c in [("origin path does not exist", f"file://{W}/nope", commit),
                      ("commit not in origin", f"file://{src}", "0" * 40),
                      ("host cannot be resolved", "https://nonexistent.invalid/x/y", commit)]:
    d2 = W / ("co_" + label.replace(" ", "_")); sleeps = []
    try:
        git_checkout_commit(url, c, d2, retries=3, sleep=sleeps.append)
    except Exception as e:  # noqa
        print(f"fetch: {label:28s} -> {type(e).__name__}(kind={getattr(e,'kind','-')}) sleeps={sleeps} | {str(e)[-90:]}")
