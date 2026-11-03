"""A-7 independent check (read-only): every tracked text file (git ls-files, so the review's untracked scratch and
.venv are out; docs/handoff and legacy excluded as D-C1-8 exempts the bundle and legacy is superseded material),
each occurrence of pre-regist*/preregist*/untouched, classified as quoted (inside '...', "...", `...` or a finding
id) or not, with D-C1-8's own exemption of the dated Checkpoint-1 report applied."""
import os
import re
import subprocess

REPO = "/home/user/MSHI"
files = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True,
                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).stdout.split("\n")
pat = re.compile(r"pre-?regist\w*|untouched", re.I)
quoted = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`|“[^”]*”|‘[^’]*’")
for f in files:
    if not f or f.startswith(("docs/handoff/", "legacy/")) or not f.endswith((".md", ".py", ".yaml", ".txt", ".cff")):
        continue
    try:
        text = open(os.path.join(REPO, f), encoding="utf-8").read()
    except (UnicodeDecodeError, FileNotFoundError):
        continue
    for i, line in enumerate(text.splitlines(), 1):
        for m in pat.finditer(line):
            spans = [q.span() for q in quoted.finditer(line)]
            inq = any(a <= m.start() < b for a, b in spans) or "not-untouched" in line[max(0, m.start() - 12):m.end()]
            if inq:
                continue
            exempt = f == "docs/CHECKPOINT1.md"
            ctx = line[max(0, m.start() - 70):m.end() + 50].replace("\n", " ")
            print(f"{'EXEMPT ' if exempt else 'UNQUOTED'} {f}:{i}: ...{ctx}...")
