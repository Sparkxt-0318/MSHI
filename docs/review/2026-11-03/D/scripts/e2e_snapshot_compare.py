"""Snapshot (copy) the sandbox outputs, or compare two snapshots file by file (SHA-256).

    e2e_snapshot_compare.py snap <sb> <dest>
    e2e_snapshot_compare.py cmp <snapA> <snapB>
run_log.jsonl is excluded (it holds timestamps by design).
"""
import hashlib
import shutil
import sys
from pathlib import Path

SUBS = ("results", "figures", "interim", "derived")


def files(root: Path) -> dict:
    out = {}
    for sub in SUBS:
        for p in sorted((root / sub).rglob("*")):
            if p.is_file() and p.name != "run_log.jsonl":
                out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


if sys.argv[1] == "snap":
    sb, dest = Path(sys.argv[2]), Path(sys.argv[3])
    if dest.exists():
        shutil.rmtree(dest)
    for sub in SUBS:
        if (sb / sub).exists():
            shutil.copytree(sb / sub, dest / sub)
    print(f"snapshot {dest}: {len(files(dest))} files")
else:
    a, b = files(Path(sys.argv[2])), files(Path(sys.argv[3]))
    same = [k for k in a if k in b and a[k] == b[k]]
    diff = [k for k in a if k in b and a[k] != b[k]]
    print(f"{len(same)} identical; {len(diff)} differ; only in A: {sorted(set(a) - set(b))}; "
          f"only in B: {sorted(set(b) - set(a))}")
    for k in diff:
        print("DIFFERS:", k)
