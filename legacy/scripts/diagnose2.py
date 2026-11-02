"""Try simpler model + climate-only baseline + variance check."""
import numpy as np, pandas as pd
from sklearn.model_selection import KFold
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import xgboost as xgb

train = pd.read_parquet("data/processed/training_features.parquet")
us    = pd.read_parquet("data/processed/us_validation_features.parquet")

target = "log_rs_annual"
drop = {target, "rs_annual", "longitude", "latitude", "site_id", "source", "region"}
all_feats = [c for c in train.columns if c not in drop]
climate = ["bio01", "bio04", "bio12", "bio14", "bio15"]

tr = train.dropna(subset=[target] + all_feats).reset_index(drop=True)
te = us.dropna(subset=[target] + all_feats).reset_index(drop=True)

print(f"Train log_rs_annual: mean={tr[target].mean():.3f}  std={tr[target].std():.3f}  var={tr[target].var():.3f}")
print(f"US    log_rs_annual: mean={te[target].mean():.3f}  std={te[target].std():.3f}  var={te[target].var():.3f}")

def eval_block(name, feats, model_factory):
    X = tr[feats].to_numpy("float32"); y = tr[target].to_numpy("float32")
    r2s = []
    for k, (a, b) in enumerate(KFold(5, shuffle=True, random_state=42).split(X)):
        m = model_factory()
        m.fit(X[a], y[a])
        r2s.append(r2_score(y[b], m.predict(X[b])))
    m = model_factory(); m.fit(X, y)
    p = m.predict(te[feats].to_numpy("float32"))
    print(f"  [{name}]  CV R2={np.mean(r2s):+.3f}  Asia->US R2={r2_score(te[target], p):+.3f}  pred_std={np.std(p):.3f}")

print("\n=== Models on all 20 features ===")
eval_block("xgb default",
           all_feats,
           lambda: xgb.XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                                    subsample=0.85, colsample_bytree=0.85, n_jobs=1, verbosity=0))
eval_block("xgb shallow",
           all_feats,
           lambda: xgb.XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                    reg_lambda=2.0, subsample=0.7, n_jobs=1, verbosity=0))
eval_block("ridge",
           all_feats,
           lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)))

print("\n=== Climate-only (5 bioclim features) ===")
eval_block("xgb climate-only",
           climate,
           lambda: xgb.XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                    reg_lambda=2.0, n_jobs=1, verbosity=0))
eval_block("ridge climate-only",
           climate,
           lambda: make_pipeline(StandardScaler(), Ridge(alpha=5.0)))

print("\n=== Soil-only (8 SoilGrids) ===")
soil = ["soc","nitrogen","phh2o","clay","sand","silt","bdod","cec"]
eval_block("xgb soil-only",
           soil,
           lambda: xgb.XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05,
                                    reg_lambda=2.0, n_jobs=1, verbosity=0))

print("\n=== Naive: predict train mean ===")
y_te = te[target].to_numpy()
print(f"  Asia->US R2(train_mean) = {r2_score(y_te, np.full_like(y_te, tr[target].mean())):.3f}")
