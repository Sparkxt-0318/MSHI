"""Replica of handoff cosore_aggregate.py (identical logic, local paths) + diagnostics.
Usage: python -I cosore_replica.py COSORE_DATASETS_DIR OUT_DIR"""
import sys, warnings, csv, io, traceback, json
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore", category=UserWarning, module="rdata")
import rdata
ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
K = 12.011 * 31_536_000.0 / 1_000_000.0

def parse_description(path):
    out = {}
    if not path.exists(): return out
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if ":" in line:
            k, _, v = line.partition(":"); out[k.strip()] = v.strip()
    return out

def parse_ports(path):
    if not path.exists(): return pd.DataFrame()
    lines = [l for l in path.read_text(errors="replace").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    rd = csv.reader(io.StringIO("\n".join(lines)), skipinitialspace=True)
    rows = [[c.strip().strip('"').strip() for c in r] for r in rd]
    hdr = rows[0]; body = [r + [""] * (len(hdr) - len(r)) for r in rows[1:]]
    return pd.DataFrame([r[:len(hdr)] for r in body], columns=hdr)

fails, per_port, sites = [], [], []
datasets = sorted([d for d in ROOT.iterdir() if d.is_dir()])
cnt = dict(ok=0, meta=0, data=0, noq=0)
for ds in datasets:
    if ds.name.startswith("TEST"): continue
    meta = parse_description(ds / "DESCRIPTION.txt")
    try:
        lat = float(meta.get("CSR_LATITUDE", "")); lon = float(meta.get("CSR_LONGITUDE", ""))
    except (TypeError, ValueError):
        cnt["meta"] += 1; fails.append((ds.name, "meta", "")); continue
    rds = ds / "data" / "data.RDS"
    try:
        df = rdata.conversion.convert(rdata.parser.parse_file(rds))
    except Exception as e:
        cnt["data"] += 1; fails.append((ds.name, "parse", f"{type(e).__name__}: {str(e)[:150]}")); continue
    if not isinstance(df, pd.DataFrame) or "CSR_FLUX_CO2" not in df.columns or "CSR_PORT" not in df.columns or "CSR_TIMESTAMP_BEGIN" not in df.columns:
        cnt["data"] += 1; fails.append((ds.name, "columns", str(list(df.columns))[:150] if isinstance(df, pd.DataFrame) else str(type(df)))); continue
    ports_meta = parse_ports(ds / "PORTS.txt")
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    df["t"] = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce"); df = df.dropna(subset=["t"])
    df["day"] = df["t"].dt.normalize()
    rows = []
    for port, g in df.groupby("CSR_PORT"):
        n_days = g["day"].nunique(); span = (g["day"].max() - g["day"].min()).days
        rec = {"ds": ds.name, "port": int(port), "n": len(g), "n_days": n_days, "span_days": span,
               "qual": bool(n_days >= 150 and span >= 180)}
        f = g["CSR_FLUX_CO2"]
        rec["mean_clip"] = float(f.clip(-2, 50).mean()); rec["mean_raw"] = float(f.mean())
        rec["mean_drop"] = float(f[(f >= -2) & (f <= 50)].mean())
        rec["frac_hi"] = float((f > 50).mean()); rec["frac_lo"] = float((f < -2).mean())
        m = g["t"].dt.month
        rec["n_months"] = int(m.nunique())
        # month-balanced: mean of daily means within month (across years), then mean over months present
        dm = g.assign(fc=f.clip(-2, 50)).groupby("day")["fc"].mean()
        mm = dm.groupby(dm.index.month).mean()
        rec["mean_daybal"] = float(dm.mean()); rec["mean_monthbal_present"] = float(mm.mean())
        rec["months_present"] = "".join("x" if k in mm.index else "." for k in range(1, 13))
        rec["first"] = str(g["day"].min().date()); rec["last"] = str(g["day"].max().date())
        if len(ports_meta) and "CSR_PORT" in ports_meta:
            pm = ports_meta[ports_meta["CSR_PORT"].astype(str).str.strip() == str(int(port))]
            if len(pm) == 0: pm = ports_meta[ports_meta["CSR_PORT"].astype(str).str.strip() == "0"]
            rec["msmt_var"] = pm["CSR_MSMT_VAR"].iloc[0] if len(pm) and "CSR_MSMT_VAR" in pm else ""
            rec["treatment"] = pm["CSR_TREATMENT"].iloc[0] if len(pm) and "CSR_TREATMENT" in pm else ""
        rows.append(rec)
    per_port.extend(rows)
    q = [r for r in rows if r["qual"]]
    if not q: cnt["noq"] += 1; fails.append((ds.name, "noqual", "")); continue
    rs_site = float(np.mean([r["mean_clip"] * K for r in q]))
    if not (50 <= rs_site <= 4500): cnt["noq"] += 1; fails.append((ds.name, "range", rs_site)); continue
    sites.append({"site_id": f"cosore_{ds.name}", "source": "cosore", "longitude": lon, "latitude": lat, "rs_annual": rs_site,
                  "n_ports_qualifying": len(q), "site_name": meta.get("CSR_SITE_NAME", ""), "igbp": meta.get("CSR_IGBP", "")})
    cnt["ok"] += 1
pd.DataFrame(sites).to_csv(OUT / "cosore_annual.csv", index=False)
pd.DataFrame(per_port).to_csv(OUT / "cosore_ports_diag.csv", index=False)
pd.DataFrame(fails, columns=["ds", "why", "detail"]).to_csv(OUT / "cosore_fails.csv", index=False)
print(cnt)
