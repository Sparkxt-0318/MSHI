# Does exp_matrix's input path (float64 DataFrame) vs clean_test's (float32 numpy) change XGB predictions under the same version?
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.metrics import r2_score
C8 = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio14", "bio15", "bio17"]
P = dict(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, min_child_weight=4,
         reg_alpha=0.5, reg_lambda=2.0, n_jobs=2, verbosity=0, random_state=0)
Pp = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed/"
a = pd.read_parquet(Pp + "training_features_v2.parquet").dropna(subset=C8 + ["log_rs_annual"])
u = pd.read_parquet(Pp + "us_validation_features_v2.parquet").dropna(subset=C8 + ["log_rs_annual"])
p1 = xgb.XGBRegressor(**P).fit(a[C8], a.log_rs_annual).predict(u[C8])                                    # exp_matrix style
p2 = xgb.XGBRegressor(**P).fit(a[C8].to_numpy("float32"), a.log_rs_annual.values).predict(u[C8].to_numpy("float32"))  # clean_test style
print("xgboost", xgb.__version__, "max |p1-p2| =", float(np.max(np.abs(p1 - p2))), " r2:", r2_score(u.log_rs_annual, p1), r2_score(u.log_rs_annual, p2))
