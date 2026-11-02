"""Attach PROXY climate (bio01, bio12) to the N2b-like sample: nearest original-pipeline site (training_features_v2 /
us_validation_features_v2) within MAXKM; v3 WorldClim 2.5' is not available offline."""
import sys, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
S, P, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
MAXKM = 10.0
d = pd.read_parquet(S)
o = pd.concat([pd.read_parquet(P + "training_features_v2.parquet"), pd.read_parquet(P + "us_validation_features_v2.parquet")], ignore_index=True)
o = o.dropna(subset=["bio01", "bio12"])
t = BallTree(np.radians(o[["latitude", "longitude"]].values), metric="haversine")
dist, idx = t.query(np.radians(d[["lat", "lon"]].values), k=1)
d["proxy_km"] = dist[:, 0] * 6371.0
d["bio01"] = o.bio01.values[idx[:, 0]]; d["bio12"] = o.bio12.values[idx[:, 0]]
print("distance to nearest original site (km): quantiles", np.round(np.quantile(d.proxy_km, [.5, .9, .95, .99, 1]), 2))
print("matched within", MAXKM, "km:", int((d.proxy_km <= MAXKM).sum()), "of", len(d))
d.loc[d.proxy_km > MAXKM, ["bio01", "bio12"]] = np.nan
d["lnP"] = np.log(d.bio12)
d.to_parquet(OUT)
