"""PORTS.txt: mshi.data.cosore.parse_ports vs an independent char-level parser on every dataset, and the
claim 'without turning tabs into spaces, quoted fields with commas split; 5 files did not parse' (D-P2-1)."""
import csv, io, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, str(Path(__file__).parent))
from mshi.data.cosore import parse_ports
from cosore_indep import ports_txt
DS = Path("/home/user/MSHI/data/raw/cosore/02f32e8e/inst/extdata/datasets")
diff, bad_notab, n = [], [], 0
for ds in sorted(d for d in DS.iterdir() if d.is_dir() and not d.name.startswith("TEST")):
    p = ds / "PORTS.txt"
    if not p.exists():
        print("no PORTS.txt:", ds.name); continue
    n += 1
    a, b = parse_ports(p), ports_txt(p)
    if a != b:
        diff.append(ds.name)
        print("DIFF", ds.name, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)})
    # without the tab replacement
    lines = [ln for ln in p.read_text(errors="replace").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(lines)), skipinitialspace=True))
    hdr = [c.strip() for c in rows[0]]
    if any(len(r) > len(hdr) for r in rows[1:]):
        bad_notab.append(ds.name)
    vals = {c.strip() for r in rows[1:] for c in r}
print("datasets with PORTS.txt:", n, "; parse_ports != independent parser:", len(diff))
print("files where rows have more fields than the header without the tab replacement:", len(bad_notab), bad_notab)
# what values of CSR_MSMT_VAR / CSR_TREATMENT exist, and port keys that are not plain integers
import collections
mv, tr, oddport = collections.Counter(), collections.Counter(), []
for ds in sorted(d for d in DS.iterdir() if d.is_dir() and not d.name.startswith("TEST")):
    p = ds / "PORTS.txt"
    if not p.exists(): continue
    for k, r in parse_ports(p).items():
        mv[r.get("CSR_MSMT_VAR")] += 1; tr[r.get("CSR_TREATMENT")] += 1
    lines = [ln for ln in p.read_text(errors="replace").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    for ln in lines[1:]:
        f0 = ln.split(",")[0].strip().strip('"')
        if not f0.lstrip("-").isdigit(): oddport.append((ds.name, f0))
print("CSR_MSMT_VAR values:", dict(mv)); print("CSR_TREATMENT values:", dict(tr)); print("non-integer port keys:", oddport)
