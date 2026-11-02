"""E4b: 2x2 train-region x test-region, R2 and RMSE (log), plus test-set SD. Site-mean target, v3 repo sites, C8 XGB."""
import json, sys
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score
C8 = ["bio01","bio04","bio05","bio06","bio12","bio14","bio15","bio17"]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4, reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0, random_state=0)
d = pd.read_parquet(sys.argv[1]).dropna(subset=C8+["log_rs"])
box_a = d.lon.between(25,180) & d.lat.between(-10,80); box_u = d.lon.between(-125,-66) & d.lat.between(24,50)
cont_a = d.continent.eq("Asia"); cont_u = d.continent.eq("North America")
R = {}
for tn, tm in [("Asia continent", cont_a), ("Asia box", box_a)]:
    m = xgb.XGBRegressor(**P).fit(d[tm][C8], d[tm].log_rs)
    for un, um in [("NA continent", cont_u), ("US box", box_u), ("NA continent minus US box", cont_u & ~box_u)]:
        u = d[um]; p = m.predict(u[C8])
        R[f"{tn} -> {un}"] = dict(n=len(u), r2=round(float(r2_score(u.log_rs, p)),3), rmse_log=round(float(np.sqrt(np.mean((p-u.log_rs)**2))),3),
                                  test_sd=round(float(u.log_rs.std()),3), rmse_intercept=round(float(np.sqrt(np.mean((d[tm].log_rs.mean()-u.log_rs)**2))),3))
for k,v in R.items(): print(f"{k:45s} {v}")
u = d[cont_u & ~box_u]; print(u.country.value_counts().head(8).to_dict())
json.dump(R, open(sys.argv[2],"w"), indent=1)
