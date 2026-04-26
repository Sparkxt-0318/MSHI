"""Quick diagnostic: random KFold ceiling + Asia→US transfer + drift."""
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.metrics import r2_score, mean_squared_error
import xgboost as xgb

train = pd.read_parquet("data/processed/training_features.parquet")
us = pd.read_parquet("data/processed/us_validation_features.parquet")
target = "log_rs_annual"
drop = {target, "rs_annual", "longitude", "latitude", "site_id", "source", "region"}
feats = [c for c in train.columns if c not in drop]
print("features:", feats)

tr = train.dropna(subset=[target] + feats).reset_index(drop=True)
te = us.dropna(subset=[target] + feats).reset_index(drop=True)
print(f"train rows: {len(tr)}  us rows: {len(te)}")

X, y = tr[feats].to_numpy("float32"), tr[target].to_numpy("float32")
r2s = []
for k, (a, b) in enumerate(KFold(5, shuffle=True, random_state=42).split(X)):
    m = xgb.XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                         subsample=0.85, colsample_bytree=0.85, verbosity=0, n_jobs=1)
    m.fit(X[a], y[a])
    r2s.append(r2_score(y[b], m.predict(X[b])))
print(f"\nRandom KFold (in-distribution): R2 mean = {np.mean(r2s):.3f}  per-fold = {[round(r,3) for r in r2s]}")

m = xgb.XGBRegressor(n_estimators=400, max_depth=5, learning_rate=0.05,
                     subsample=0.85, colsample_bytree=0.85, verbosity=0, n_jobs=1)
m.fit(X, y)
p_us = m.predict(te[feats].to_numpy("float32"))
y_us = te[target].to_numpy("float32")
print(f"Asia -> US transfer R2 = {r2_score(y_us, p_us):.3f}  rmse={np.sqrt(mean_squared_error(y_us, p_us)):.3f}")
print(f"  US y range: {y_us.min():.2f} .. {y_us.max():.2f}, mean {y_us.mean():.2f}")
print(f"  US pred range: {p_us.min():.2f} .. {p_us.max():.2f}, mean {p_us.mean():.2f}")

print("\nFeature distribution drift (US mean shift in sigma_train units):")
for f in feats:
    a, b = tr[f], te[f]
    mu_t, sd_t = a.mean(), max(a.std(), 1e-9)
    drift = (b.mean() - mu_t) / sd_t
    coverage = ((b >= a.min()) & (b <= a.max())).mean()
    flag = "  WARN" if abs(drift) > 0.5 or coverage < 0.9 else ""
    print(f"  {f:<22s} drift={drift:+.2f}sd  in-train-range={coverage*100:5.1f}%{flag}")
