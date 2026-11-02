"""Synthetic features table (real v3 coordinates/continents, synthetic predictors) to exercise clean_test.py code paths.
No plan .md file is placed next to it; the .sha256 sidecar holds an arbitrary string."""
import sys
import numpy as np, pandas as pd
W = sys.argv[1]
rng = np.random.default_rng(0)
a = pd.read_parquet(f"{W}/out/asia_384.parquet"); e = pd.read_parquet(f"{W}/out/europe_235.parquet")
d = pd.concat([a.assign(continent="Asia"), e.assign(continent="Europe")], ignore_index=True)
n = len(d); eu = (d.continent == "Europe").values
for i in [1, 4, 5, 6, 12, 14, 15, 17]:
    d[f"bio{i:02d}"] = rng.normal(0, 1, n)
d["bio01"] = np.where(eu, rng.normal(3, 2, n), rng.normal(0, 1, n))       # Europe partly outside Asia range -> AOA branch runs
d["bio12"] = np.exp(rng.normal(6.5, 0.4, n))
for c in ["soc", "nitrogen", "phh2o", "clay", "sand", "silt", "bdod", "cec", "npp", "lst_day", "lst_night", "lst_diurnal_range"]:
    d[c] = rng.normal(0, 1, n)
d["log_rs"] = 6.5 + 0.15 * d.bio01 + 0.3 * (np.log(d.bio12) - 6.5) + rng.normal(0, 0.5, n)
d.to_parquet(f"{W}/synth/features_synth.parquet")
open(f"{W}/synth/ANALYSIS_PLAN_LOCKED.sha256", "w").write("NOT-A-REAL-HASH  ANALYSIS_PLAN_LOCKED.md\n")
print(d.continent.value_counts().to_dict())
