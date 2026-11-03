"""What are the duplicated (port, CSR_TIMESTAMP_BEGIN) rows in the kept COSORE ports, and how much do they
move the analysis annual value (D-P2-1)? Variants: as the pipeline (all rows), exact-duplicate rows dropped,
one value per (port, timestamp) (mean)."""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import rdata

REPO = Path("/home/user/MSHI")
DS = REPO / "data/raw/cosore/02f32e8e/inst/extdata/datasets"
FACTOR = 12.011 * 31536000 / 1e6
P = pd.read_csv(Path(__file__).resolve().parents[1] / "logs" / "cosore_indep_ports.csv")
kept = P[P.kept_utc]


def annual(g):
    fc = g.CSR_FLUX_CO2.clip(-2.0, 50.0)
    day = pd.to_datetime(g.CSR_TIMESTAMP_BEGIN, unit="s").dt.normalize()
    daily = fc.groupby(day).mean()
    mon = daily.groupby(daily.index.month).mean()
    return float(mon.mean() * FACTOR) if len(mon) == 12 else np.nan


rows = []
for ds in sorted(kept.dataset.unique()):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = rdata.conversion.convert(rdata.parser.parse_file(DS / ds / "data" / "data.RDS"))
    d = df.dropna(subset=["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"])
    ports = kept[kept.dataset == ds].port.tolist()
    site = {"all": [], "dedup_exact": [], "mean_per_ts": []}
    for port in ports:
        g = d[d.CSR_PORT == port]
        dupmask = g.duplicated(["CSR_TIMESTAMP_BEGIN"], keep=False)
        if dupmask.any() and ds in ("d20200108_JASSAL", "d20200122_BLACK", "d20190409_ANJILELI") and port == ports[0]:
            ex = g[dupmask].sort_values("CSR_TIMESTAMP_BEGIN").head(6)
            print(ds, "port", port, "example duplicated rows (all columns):")
            print(ex.to_string(max_cols=20))
            same = g[dupmask].groupby("CSR_TIMESTAMP_BEGIN").CSR_FLUX_CO2.nunique()
            print("   timestamps with >1 distinct flux:", int((same > 1).sum()), "of", len(same))
        a_all = annual(g)
        a_ex = annual(g.drop_duplicates())
        gm = g.groupby("CSR_TIMESTAMP_BEGIN", as_index=False).CSR_FLUX_CO2.mean()
        a_m = annual(gm)
        site["all"].append(a_all)
        site["dedup_exact"].append(a_ex)
        site["mean_per_ts"].append(a_m)
    rows.append({"dataset": ds, **{k: float(np.mean(v)) for k, v in site.items()}})
R = pd.DataFrame(rows)
R["rel_exact"] = R.dedup_exact / R["all"] - 1
R["rel_meanTS"] = R.mean_per_ts / R["all"] - 1
pd.set_option("display.width", 200)
print(R.sort_values("rel_meanTS", key=abs, ascending=False).to_string())
print("max |rel| exact-dedup: %.4f, per-timestamp mean: %.4f" % (R.rel_exact.abs().max(), R.rel_meanTS.abs().max()))
