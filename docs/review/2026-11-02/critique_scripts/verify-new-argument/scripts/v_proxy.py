"""Verifier's own PROXY inputs (WorldClim 2.5' is unavailable offline).
Sites: v3 QC sites rebuilt here with the verbatim handoff build_sites_v3.py; bio01/bio12 from the nearest
original-pipeline site (training_features_v2 / us_validation_features_v2) if within MAXKM, else from the
0.5-deg atlas cell containing the site (legacy atlas_lookup.json, WorldClim 10').
Cells: 0.5-deg cell centre climate from atlas_lookup.json; cells missing from the atlas filled from the
nearest atlas cell within 1 deg (flag 'filled').
"""
import sys, json, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
V = sys.argv[1]; P = sys.argv[2]; ATLAS = sys.argv[3]; MAXKM = 10.0
d = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
o = pd.concat([pd.read_parquet(P + "/training_features_v2.parquet"), pd.read_parquet(P + "/us_validation_features_v2.parquet")], ignore_index=True)
o = o.dropna(subset=["bio01", "bio12"])
t = BallTree(np.radians(o[["latitude", "longitude"]].values), metric="haversine")
dist, idx = t.query(np.radians(d[["lat", "lon"]].values), k=1)
d["proxy_km"] = dist[:, 0] * 6371.0
d["bio01_o"] = o.bio01.values[idx[:, 0]]; d["bio12_o"] = o.bio12.values[idx[:, 0]]
cells = json.load(open(ATLAS))["cells"]
clim = pd.DataFrame([(c["lat"], c["lon"], c["fnpp"]["features"]["bio01"], c["fnpp"]["features"]["bio12"]) for c in cells], columns=["lat", "lon", "bio01", "bio12"])
clim["cx"] = np.floor(clim.lon / 0.5).astype(int); clim["cy"] = np.floor(clim.lat / 0.5).astype(int)
clim.to_parquet(f"{V}/out/atlas_clim.parquet")
key = dict(zip(zip(clim.cx, clim.cy), zip(clim.bio01, clim.bio12)))
cxy = list(zip(np.floor(d.lon / 0.5).astype(int), np.floor(d.lat / 0.5).astype(int)))
d["bio01_a"] = [key.get(k, (np.nan, np.nan))[0] for k in cxy]; d["bio12_a"] = [key.get(k, (np.nan, np.nan))[1] for k in cxy]
use_o = d.proxy_km <= MAXKM
d["bio01"] = np.where(use_o, d.bio01_o, d.bio01_a); d["bio12"] = np.where(use_o, d.bio12_o, d.bio12_a)
d["clim_src"] = np.where(use_o, "orig_site", np.where(d.bio01_a.notna(), "atlas_cell", "none"))
d.to_parquet(f"{V}/out/sites_qc_proxy.parquet")
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
s = d[inbox & d.continent.isin(["Asia", "North America"])]
print("in-box Asia+NA sites:", len(s), " proxy_km quantiles", np.round(np.quantile(s.proxy_km, [.5, .9, .95, .99, 1]), 2))
print(s.clim_src.value_counts().to_dict())
