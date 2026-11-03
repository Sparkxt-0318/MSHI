"""Check 3f: point fits of the repo variant (phase2.variant = repo is a configured sensitivity): candidates, kept fit
vs bounded REML maximum."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import copy, warnings
import numpy as np, pandas as pd
from threadpoolctl import threadpool_limits
from common import REPO
from fastreml import suffstats, reml_max
from mshi.analysis import noise_ceiling as NC
from mshi.config import load_config, Config
warnings.simplefilter("ignore")
cfg = load_config()
data = copy.deepcopy(cfg.data); data["phase2"]["variant"] = "repo"
S = NC.Settings.from_cfg(Config(data))
rec = pd.read_parquet(f"{REPO}/data/derived/records_analysis.parquet")
sites = pd.read_parquet(f"{REPO}/data/derived/sites_analysis_repo.parquet")
rr, sst, info = NC.prepare(rec, sites, S)
groups = NC.build_groups(rr, sst, S.continents)
with threadpool_limits(limits=1):
    for name, g in groups.items():
        y, site, study = NC.replicate(g, np.arange(len(g.site_ids)), S.min_records)
        fit = NC.fit_nested(y, site, study, S.optimizer)
        th, llf = reml_max(suffstats(y, site, study), y_var=np.var(y))
        c = fit.get("candidates", {})
        kept = c[fit["chosen"]]["llf"] if fit["status"] == "ok" else None
        print(f"{name:14s} status {fit['status']} kept {fit.get('chosen')} llf {kept} | REML max llf {llf:.6f} s2 {np.round(th,5).tolist()} | "
              + "; ".join(f"{k}: usable {v['usable']} llf {v['llf']}" for k, v in c.items()))
