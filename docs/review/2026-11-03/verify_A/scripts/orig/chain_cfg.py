import copy, sys
from pathlib import Path
sys.path.insert(0, "/home/user/MSHI")
from mshi.config import Config, load_config
NAME = "chain"
BASE = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/A/sb") / NAME
def make_cfg() -> Config:
    cfg0 = load_config()
    d = copy.deepcopy(cfg0.data)
    for root in ("raw", "interim", "derived", "results", "figures"):
        d["paths"][root] = str(BASE / root)
    p2 = d["phase2"]
    p2["noise_ceiling"].update(n_boot=10, n_jobs=1)
    p2["transfer"]["rf"].update(n_estimators=8, grid={"min_samples_leaf": [2, 8], "max_features": [0.5, 1.0]},
                                inner_folds=3, n_jobs=1)
    p2["transfer"]["xgb_light"] = {**d["clean_test"]["locked"]["xgb"], "n_estimators": 12}
    p2["transfer"]["xgb_from"] = "phase2.transfer.xgb_light"
    p2["within"].update(folds=2, seeds=[42, 43])
    p2["within"]["knndm"].update(max_pred_points=300)
    p2["bootstrap"]["n"] = 60
    p2["aoa"].update(perm_repeats=2)
    p2["us_r2"].update(xgb_seed_spread=[0, 1])
    return Config(d, source=cfg0.source)


