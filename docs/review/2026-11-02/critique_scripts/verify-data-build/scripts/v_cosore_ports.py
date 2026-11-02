"""Independent COSORE port-level diagnostics (findings 02, 03, 07). Reads data only (rdata parser); executes no repo code.
For each non-TEST dataset: why it is skipped (missing file / parse error / no qualifying port / out of range),
and for each port that qualifies under cosore_aggregate.py rules: PORTS.txt attributes (port row or port-0 fallback),
clip-mean (as handoff), drop-mean, months covered, monthly climatology (mean of daily means per calendar month)."""
import sys, csv, io, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import rdata
from pathlib import Path
ROOT = Path("/home/user/MSHI/data/raw/cosore/repo/inst/extdata/datasets"); OUT = Path(sys.argv[1])
K = 12.011 * 31_536_000.0 / 1e6

def desc(p):
    out = {}
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and ":" in line:
            k, _, v = line.partition(":"); out[k.strip()] = v.strip()
    return out

def ports_txt(p):
    if not p.exists(): return None
    lines = [l for l in p.read_text(errors="replace").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(lines)), skipinitialspace=True))
    hdr = [h.strip() for h in rows[0]]
    recs = [dict(zip(hdr, [x.strip() for x in r])) for r in rows[1:]]
    return {int(r["CSR_PORT"]): r for r in recs if r.get("CSR_PORT", "").strip().lstrip("-").isdigit()}

fails, prow, mrow = [], [], []
for ds in sorted(d for d in ROOT.iterdir() if d.is_dir() and not d.name.startswith("TEST")):
    rds = ds / "data" / "data.RDS"
    if not rds.exists(): fails.append((ds.name, "data.RDS missing")); continue
    try:
        df = rdata.conversion.convert(rdata.parser.parse_file(rds))
    except Exception as e:
        fails.append((ds.name, f"parse error {type(e).__name__}")); continue
    if not isinstance(df, pd.DataFrame) or not {"CSR_FLUX_CO2", "CSR_PORT", "CSR_TIMESTAMP_BEGIN"} <= set(df.columns):
        fails.append((ds.name, f"columns missing: {sorted(set(['CSR_FLUX_CO2','CSR_PORT','CSR_TIMESTAMP_BEGIN']) - set(getattr(df,'columns',[])))}")); continue
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna().copy()
    df["t"] = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce"); df = df.dropna(subset=["t"]); df["day"] = df.t.dt.normalize()
    P = ports_txt(ds / "PORTS.txt") or {}
    q = 0
    for port, g in df.groupby("CSR_PORT"):
        nd = g.day.nunique(); span = (g.day.max() - g.day.min()).days
        if nd < 150 or span < 180: continue
        q += 1
        f = g.CSR_FLUX_CO2
        meta = P.get(int(port), P.get(0, {}))
        daily = g.assign(fc=f.clip(-2, 50)).groupby("day").fc.mean()
        mon = daily.groupby(daily.index.month).mean()
        prow.append(dict(ds=ds.name, port=int(port), n=len(g), n_days=nd, span=span, years=g.t.dt.year.nunique(),
                         msmt=meta.get("CSR_MSMT_VAR", "?"), trt=meta.get("CSR_TREATMENT", "?"), opaque=meta.get("CSR_OPAQUE", ""),
                         meta_port=(int(port) if int(port) in P else (0 if 0 in P else None)),
                         raw_mean=float(f.mean()), clip_mean=float(f.clip(-2, 50).mean()), drop_mean=float(f[(f >= -2) & (f <= 50)].mean()),
                         frac_hi=float((f > 50).mean()), frac_lo=float((f < -2).mean()), n_months=int(mon.size),
                         month_bal_mean=float(mon.mean()), daily_bal_mean=float(daily.mean())))
        for mth, v in mon.items(): mrow.append(dict(ds=ds.name, port=int(port), month=int(mth), mean=float(v)))
    if q == 0: fails.append((ds.name, "parsed OK; no port with >=150 days & >=180-day span"))
pr = pd.DataFrame(prow); pr.to_csv(OUT / "ports_diag.csv", index=False); pd.DataFrame(mrow).to_csv(OUT / "ports_monthly.csv", index=False)
fl = pd.DataFrame(fails, columns=["ds", "reason"]); fl.to_csv(OUT / "fails.csv", index=False)
print(fl.reason.str.split(";").str[0].value_counts().to_string())
site = pr.groupby("ds").clip_mean.mean() * K
print("datasets with >=1 qualifying port:", pr.ds.nunique(), "; site rs outside 50-4500:", site[(site < 50) | (site > 4500)].round(1).to_dict())
