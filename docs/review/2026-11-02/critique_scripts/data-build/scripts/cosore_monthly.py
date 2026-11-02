"""Monthly climatology of clipped CO2 flux for every qualifying port of the 66 retained COSORE datasets."""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import rdata
ROOT, OUTD = Path(sys.argv[1]), Path(sys.argv[2])
st = pd.read_csv(OUTD / "cosore_annual.csv", keep_default_na=False)
rows = []
for sid in st.site_id:
    ds = sid.replace("cosore_", "")
    df = rdata.conversion.convert(rdata.parser.parse_file(ROOT / ds / "data" / "data.RDS"))
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    df["t"] = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce"); df = df.dropna(subset=["t"])
    df["day"] = df.t.dt.normalize()
    for port, g in df.groupby("CSR_PORT"):
        if g.day.nunique() < 150 or (g.day.max() - g.day.min()).days < 180: continue
        f = g.CSR_FLUX_CO2.clip(-2, 50)
        dm = f.groupby(g.day).mean()
        mm = dm.groupby(dm.index.month).mean()
        rec = {"ds": ds, "port": int(port), "obs_mean": float(f.mean())}
        for m in range(1, 13): rec[f"m{m:02d}"] = float(mm.get(m, np.nan))
        rows.append(rec)
pd.DataFrame(rows).to_csv(OUTD / "cosore_port_monthly.csv", index=False)
print("ports:", len(rows))
