"""Within-continent CV leakage probe: the out-of-fold predictions and nulls of fold f must not change when fold f's own
outcomes are shifted (+3) -- for every learner, on the kNNDM split of the synthetic Europe sites (real coordinates)."""
import sys, copy
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
from mshi.analysis import knndm as kn
base = load_config(); data = copy.deepcopy(base.data)
data["phase2"]["transfer"]["rf"].update(n_estimators=30, n_jobs=2)
cfg = Config(data, source=base.source); spec = T.Spec.from_cfg(cfg); K = cfg["phase2"]["within"]["knndm"]
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
sub = synth[synth.continent_geo == "Europe"].sort_values("site_id").reset_index(drop=True)
g = pd.read_parquet("ne_grid_0p5.parquet")
dom = T.prediction_domain(g, "Europe", K)
f, info = kn.knndm_folds(np.c_[sub.lon, sub.lat], dom, **{k: v for k, v in K.items() if k not in T.DOMAIN_KEYS}, earth_radius_km=6371.0)
pairs, _ = T.fold_pairs((f, info), len(sub))
for learner in ("OLS-TP", "GAM", "RF", "XGB"):
    p0, b0, fold, _ = T.oof_predict(spec, learner, sub, pairs)
    ok = True
    for k, (tr, va) in enumerate(pairs):
        s2 = sub.copy(); s2.loc[va, "log_rs"] += 3.0
        p1, b1, _, _ = T.oof_predict(spec, learner, s2, pairs)
        ok &= np.array_equal(p0[va], p1[va]) and np.array_equal(b0[va], b1[va])
    print(f"{learner}: fold predictions and nulls unchanged when the fold's own outcomes shift: {ok}")
