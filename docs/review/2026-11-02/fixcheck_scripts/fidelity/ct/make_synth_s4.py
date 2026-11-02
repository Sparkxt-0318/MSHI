"""S4: additive smooth effects over many variables (boosting-friendly) -> XGB expected. Synthetic target only."""
import sys
import numpy as np, pandas as pd
from synthlib import covariates
OUT = sys.argv[1]
d, rng = covariates(44)
z = lambda c: ((d[c] - d[c].mean()) / d[c].std()).fillna(0)
d["log_rs"] = (6.0 + 0.30 * z("bio01") + 0.20 * z("soc") - 0.18 * z("clay") + 0.15 * z("npp") + 0.12 * z("lst_night")
               + 0.10 * z("bio15") + 0.10 * z("cec") - 0.08 * z("bdod") + 0.08 * np.log(d.bio12).fillna(6.6)
               + rng.normal(0, 0.08, len(d)))
d.loc[d.index[rng.choice(len(d), 5, replace=False)], "log_rs"] = np.nan
d.to_parquet(f"{OUT}/S4_xgb.parquet", index=False)
print("written S4")
