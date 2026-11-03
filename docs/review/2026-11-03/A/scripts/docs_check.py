"""Docs vs code: what `--stage all` runs (Makefile help of `all`), the README status line, and which committed
data/derived files data/derived/README.md documents."""
import subprocess, sys, re
from pathlib import Path
REPO = Path("/home/user/MSHI")
out = subprocess.run([str(REPO / ".venv/bin/python"), "-I", "-B", "-c",
                      "import sys; sys.path.insert(0, '/home/user/MSHI'); from mshi.run import main; main(['--list'])"],
                     capture_output=True, text=True, cwd="/tmp").stdout
names = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
print("stages run by --stage all, in order:", names)
print("stages after repro_checks:", names[names.index("repro_checks") + 1:])
mk = (REPO / "Makefile").read_text()
print("Makefile `all` help:", re.search(r"^all:.*$", mk, re.M).group(0))
print("Makefile `data` target:", re.search(r"^data:[^\n]*\n[^\n]*\n[^\n]*", mk, re.M).group(0))
print("README line 3:", (REPO / "README.md").read_text().splitlines()[2])
dr = (REPO / "data/derived/README.md").read_text()
for f in sorted(p.name for p in (REPO / "data/derived").iterdir() if p.is_file() and p.name != "README.md"):
    print(f"data/derived/{f}: documented in data/derived/README.md: {f in dr}")
print("data/derived/README.md 'Produced by' line:", [l for l in dr.splitlines() if l.startswith("Produced by")])
