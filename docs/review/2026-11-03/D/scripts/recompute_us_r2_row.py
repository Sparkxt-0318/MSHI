"""Independent recomputation of us_r2 rows not covered by tests/test_us_r2.py's recomputation (which does OLS-TP, qc,
Asia -> NA outside the box): XGB, repo variant, single-record target, Asia box -> US bounding box (E4's 'boxes'
cell), and its paired target effect; from the e2e sandbox's input tables with xgboost/scikit-learn directly."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
import numpy as np
import pandas as pd
import xgboost
from sklearn.metrics import r2_score

from mshi.config import load_config
from mshi.spatial import bootstrap_ci

cfg = load_config(Path(sys.argv[1]))
R = json.loads(cfg.path("results", "us_r2.json").read_text())
C8 = cfg["phase2"]["c8"]
P = cfg["clean_test"]["locked"]["xgb"]
B = cfg["phase2"]["bootstrap"]
f = pd.read_parquet(cfg.path("interim", "features_analysis_repo.parquet"))
f = f.dropna(subset=["log_rs", "lon", "lat"] + C8 + ["bio01", "bio12"])
f = f[f.bio12 > 0].sort_values("site_id").reset_index(drop=True)
rec = pd.read_parquet(cfg.path("derived", "records_analysis.parquet"))
r = rec[rec.site_id_repo.notna()].copy()
r["k"] = (r.src != "cosore").astype(int)
r["row"] = np.where(r.src == "srdb", r.rec_id.str.replace("srdb_", "", regex=False).where(r.src == "srdb", "-1").astype(int), -1)
single = r.sort_values(["k", "row", "rec_id"]).groupby("site_id_repo").log_rs.first()
targets = {"site_mean": f.log_rs.to_numpy(), "single_record": single.loc[f.site_id].to_numpy()}
lon, lat = f.lon.to_numpy(), f.lat.to_numpy()
train = (lon >= 25) & (lon <= 180) & (lat >= -10) & (lat <= 80)
test = (lon >= -125) & (lon <= -66) & (lat >= 24) & (lat <= 50) & ~train
X = f[C8].to_numpy("float32")
out = {}
for t, y in targets.items():
    p = xgboost.XGBRegressor(**P, random_state=0).fit(X[train], y[train]).predict(X[test]).astype(float)
    row = next(x for x in R["rows"] if (x["variant"], x["target"], x["train"], x["test"], x["learner"]) ==
               ("repo", t, "Asia box", "US bounding box", "XGB"))
    r2 = r2_score(y[test], p)
    ci = bootstrap_ci(y[test], p, n=B["n"], seed=B["seed"], lon=lon[test], lat=lat[test], deg=B["block_deg"],
                      q=B["quantiles"])
    seeds = [r2_score(y[test], xgboost.XGBRegressor(**P, random_state=s).fit(X[train], y[train]).predict(X[test]))
             for s in range(cfg["phase2"]["us_r2"]["xgb_seed_spread"][0], cfg["phase2"]["us_r2"]["xgb_seed_spread"][1] + 1)]
    out[t] = (r2, p, y[test])
    print(f"{t}: n {train.sum()}/{test.sum()} vs {row['n_train']}/{row['n_test']}; r2 {r2:.10f} vs {row['r2']:.10f}; "
          f"rmse {np.sqrt(np.mean((p - y[test]) ** 2)):.10f} vs {row['rmse_log']:.10f}; CI {ci} vs {row['ci']['r2']}; "
          f"seed r2 min/mean/max {min(seeds):.6f}/{np.mean(seeds):.6f}/{max(seeds):.6f} vs "
          f"{row['seed_spread']['r2']['min']:.6f}/{row['seed_spread']['r2']['mean']:.6f}/{row['seed_spread']['r2']['max']:.6f}")
e = next(x for x in R["target_effect"] if (x["variant"], x["train"], x["test"], x["learner"]) ==
         ("repo", "Asia box", "US bounding box", "XGB"))
print(f"target effect r2: {out['site_mean'][0] - out['single_record'][0]:.10f} vs {e['r2']['difference']:.10f}; "
      f"reported paired CI {e['r2']['ci']}; seed spread of the difference {e['seed_spread_r2_difference']}")
