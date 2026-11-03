"""Leakage probe: transfer_matrix's predictions for the test continent must not depend on the test sites' outcomes or
on the other test sites' predictors (no scaling, knots, tuning or imputation from test data). Runs the real stage
twice in sandboxes: (1) synthetic table; (2) the same table with Europe's log_rs shifted by +3 and every Europe site's
predictors except site E0 perturbed. Compares predictions at E0 for every learner and training label, and the null."""
import sys, copy
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd
from mshi.config import load_config, Config
from mshi.analysis import transfer as T
from mshi.io import write_result, write_table
W0 = Path(sys.argv[1])
base = load_config()
synth = pd.read_parquet("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/B/work/synthA/out/data/interim/features_analysis_qc.parquet")
eu = synth.continent_geo.eq("Europe")
e0 = synth[eu].sort_values("site_id").site_id.iloc[0]
rng = np.random.default_rng(5)
pert = synth.copy()
pert.loc[eu, "log_rs"] += 3.0
other = eu & pert.site_id.ne(e0)
for c in ("bio01", "bio04", "bio05", "bio06", "bio14", "bio15", "bio17"):
    pert.loc[other, c] += rng.normal(0, 5, other.sum())
pert.loc[other, "bio12"] *= np.exp(rng.normal(0, 0.5, other.sum()))
res = {}
for tag, tab in (("orig", synth), ("pert", pert)):
    data = copy.deepcopy(base.data); data["paths"]["raw"] = str(W0 / tag / "raw")
    data["phase2"]["transfer"]["rf"].update(n_estimators=30, n_jobs=2); data["phase2"]["bootstrap"]["n"] = 50
    cfg = Config(data, source=base.source, out_root=W0 / tag / "out")
    paths = [write_table(tab, cfg.path("interim", f"features_analysis_{t}.parquet")) for t in ("qc", "repo")]
    write_result(cfg, {"synthetic": True}, "features_analysis.json", outputs=paths)
    T.transfer_matrix(cfg)
    tp = pd.read_parquet(cfg.path("interim", "transfer_predictions_qc.parquet"))
    res[tag] = tp[(tp.test == "Europe") & (tp.site_id == e0)].set_index(["table", "train", "learner"])[["pred_log", "null_log"]]
a, b = res["orig"].sort_index(), res["pert"].sort_index()
same = (a.pred_log.to_numpy() == b.pred_log.to_numpy()) & (a.null_log.to_numpy() == b.null_log.to_numpy())
print(f"site {e0}: {int(same.sum())} of {len(same)} (table, train, learner) predictions and nulls bit-identical")
print(a.assign(pert=b.pred_log.values, same=same).to_string())
