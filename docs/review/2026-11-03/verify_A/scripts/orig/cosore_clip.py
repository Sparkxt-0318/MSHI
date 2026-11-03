"""Kept COSORE ports (analysis rule): share of fluxes outside the clip range [-2, 50] and the effect of clipping vs
dropping them on the site value (D-P2-1 keeps the handoff's clipping)."""
import warnings
from pathlib import Path
import numpy as np, pandas as pd, rdata
DS = Path("/home/user/MSHI/data/raw/cosore/02f32e8e/inst/extdata/datasets")
F = 12.011 * 31536000 / 1e6
P = pd.read_csv(Path(__file__).resolve().parents[1] / "logs" / "cosore_indep_ports.csv")
k = P[P.kept_utc]
def annual(g, drop):
    f = g.CSR_FLUX_CO2
    if drop:
        g = g[(f >= -2) & (f <= 50)]; f = g.CSR_FLUX_CO2
    else:
        f = f.clip(-2, 50)
    day = pd.to_datetime(g.CSR_TIMESTAMP_BEGIN, unit="s").dt.normalize()
    m = f.groupby(day).mean(); m = m.groupby(m.index.month).mean()
    return m.mean() * F
rows = []
for ds in sorted(k.dataset.unique()):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = rdata.conversion.convert(rdata.parser.parse_file(DS / ds / "data" / "data.RDS"))
    d = df.dropna(subset=["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"])
    a, b, out, n = [], [], 0, 0
    for p in k[k.dataset == ds].port:
        g = d[d.CSR_PORT == p]
        out += int(((g.CSR_FLUX_CO2 < -2) | (g.CSR_FLUX_CO2 > 50)).sum()); n += len(g)
        a.append(annual(g, False)); b.append(annual(g, True))
    rows.append({"dataset": ds, "share_outside": out / n, "clip": np.mean(a), "drop": np.mean(b)})
R = pd.DataFrame(rows); R["rel"] = R["drop"] / R["clip"] - 1
print(R.sort_values("rel", key=abs, ascending=False).head(8).to_string())
print("max share outside: %.4f; max |rel| drop vs clip: %.4f" % (R.share_outside.max(), R.rel.abs().max()))
