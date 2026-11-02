import os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
from mshi.runlog import git_commit, code_sha256, PROVENANCE_PATHS

W = Path(SCR) / "work" / "t8"; shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
env = {k: v for k, v in os.environ.items() if k != "GIT_OPTIONAL_LOCKS"}      # caller WITHOUT the env var
def g(*a, cwd=W / "repo"):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()
r = W / "repo"; (r / "mshi").mkdir(parents=True); (r / "configs").mkdir(); (r / "docs").mkdir(); (r / "data/derived").mkdir(parents=True)
g("init", "-q"); g("config", "user.email", "t@example.invalid"); g("config", "user.name", "t")
(r / ".gitignore").write_text("__pycache__/\n*.pyc\ndata/interim/\n")
(r / "mshi/a.py").write_text("x = 1\n"); (r / "configs/v3.yaml").write_text("version: 3\n")
(r / "README.md").write_text("r\n"); (r / "data/derived/cosore_annual.csv").write_text("a,b\n1,2\n")
g("add", "."); g("commit", "-qm", "c")
os.environ.pop("GIT_OPTIONAL_LOCKS", None)            # prove git_commit sets it itself
def show(label):
    print(f"  {label:58s} -> {git_commit(r)}")
show("clean")
(r / "README.md").write_text("changed\n"); show("README.md modified (outside provenance paths)")
(r / "data/derived/cosore_annual.csv").write_text("a,b\n9,9\n"); show("committed input table data/derived/*.csv modified")
g("checkout", "--", ".")
(r / "mshi/new_module.py").write_text("y = 2\n"); show("untracked mshi/new_module.py")
(r / "mshi/new_module.py").unlink()
(r / "mshi/__pycache__").mkdir(); (r / "mshi/__pycache__/a.cpython-313.pyc").write_bytes(b"x"); show("ignored mshi/__pycache__/*.pyc")
# index writes: make the stat info stale, then call git_commit
idx = r / ".git/index"; before = idx.stat().st_mtime_ns
time.sleep(1.1); os.utime(r / "mshi/a.py", None)
git_commit(r)
print("  .git/index rewritten by git_commit after a stat change:", idx.stat().st_mtime_ns != before)
subprocess.run(["git", "status", "--porcelain"], cwd=r, capture_output=True, env=env)
print("  control: plain 'git status' (optional locks on) rewrites it:", idx.stat().st_mtime_ns != before)
