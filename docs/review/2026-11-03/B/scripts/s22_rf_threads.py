"""RF fit thread count (rf.n_jobs) does not change the tuned forest or its predictions: fit_learner('RF') with n_jobs 1
vs 2 (the review is limited to 2 threads), real grid, 60 trees, on the synthetic Asia+Europe sites of synthA."""
import sys, copy
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
base = load_config()
d = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
d = d[d.continent_geo.isin(["Asia", "Europe"])].sort_values("site_id").reset_index(drop=True)
out = {}
for nj in (1, 2):
    data = copy.deepcopy(base.data); data["phase2"]["transfer"]["rf"].update(n_estimators=60, n_jobs=nj)
    spec = T.Spec.from_cfg(Config(data, source=base.source))
    m = T.fit_learner(spec, "RF", d)
    out[nj] = (m.info, m.predict(d))
print("tuned params equal:", out[1][0] == out[2][0], out[1][0])
print("predictions bit-identical:", np.array_equal(out[1][1], out[2][1]))
