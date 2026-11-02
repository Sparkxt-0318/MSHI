import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.io import read_table
out = sys.argv[1]
cfg = load_config()
st = read_table(cfg, cfg.path("derived", "sites_v3_qc.parquet"))
d = st[["site_id", "lat", "lon", "continent"]].copy()
rng = np.random.default_rng(0)
n = len(d)
cols = sorted(set().union(*map(set, cfg["clean_test"]["locked"]["sets"].values())))
for c in cols:
    d[c] = rng.normal(0, 1, n)
d["bio12"] = np.exp(rng.normal(6.5, 0.4, n))
d.loc[d.index[::17], "npp"] = np.nan            # some missing predictors (dropna paths)
d1 = d.copy()
d1["log_rs"] = 6.5 + 0.15 * d1.bio01 + 0.3 * (np.log(d1.bio12) - 6.5) + rng.normal(0, 0.5, n)
d1.to_parquet(f"{out}/synth_ols.parquet", index=False)
d2 = d.copy()
d2["log_rs"] = (6 + 0.8 * np.sin(2 * d2.bio04) + 0.6 * (d2.clay > 0) * d2.soc + 0.5 * np.abs(d2.lst_day)
                + 0.4 * np.tanh(3 * d2.sand) + rng.normal(0, 0.15, n))
d2.to_parquet(f"{out}/synth_xgb.parquet", index=False)
print(d.continent.value_counts().to_dict())
