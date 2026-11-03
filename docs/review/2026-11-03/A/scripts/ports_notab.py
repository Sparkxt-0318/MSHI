import csv, io, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, "/home/user/MSHI")
from mshi.data.cosore import parse_ports
DS = Path("/home/user/MSHI/data/raw/cosore/02f32e8e/inst/extdata/datasets")
fail_pd, fail_pd2, changed = [], [], []
for ds in sorted(d for d in DS.iterdir() if d.is_dir() and not d.name.startswith("TEST")):
    p = ds / "PORTS.txt"
    if not p.exists(): continue
    try:
        pd.read_csv(p, comment="#", skipinitialspace=True)
    except Exception as e:
        fail_pd.append((ds.name, str(e)[:60]))
    try:
        pd.read_csv(p, comment="#", sep=r"\s*,\s*", engine="python")
    except Exception as e:
        fail_pd2.append(ds.name)
    # the mshi parser without the tab replacement
    lines = [ln for ln in p.read_text(errors="replace").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    rows = [[c.strip().strip('"').strip() for c in r] for r in csv.reader(io.StringIO("\n".join(lines)), skipinitialspace=True)]
    hdr = rows[0]
    recs = {int(r["CSR_PORT"]): r for r in (dict(zip(hdr, r + [""] * (len(hdr) - len(r)))) for r in rows[1:]) if r.get("CSR_PORT", "").lstrip("-").isdigit()}
    a = parse_ports(p)
    key = lambda d: {k: (v.get("CSR_MSMT_VAR"), v.get("CSR_TREATMENT")) for k, v in d.items()}
    if key(recs) != key(a):
        changed.append(ds.name)
print("pandas read_csv(comment='#', skipinitialspace=True) fails on", len(fail_pd), fail_pd)
print("no-tab-replacement csv parse changes MSMT_VAR/TREATMENT decisions in", len(changed), changed)
