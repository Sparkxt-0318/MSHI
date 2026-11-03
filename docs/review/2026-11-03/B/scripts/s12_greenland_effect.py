"""Effect of the Greenland ice sheet in North America's kNNDM prediction domain on the within-continent benchmark:
real NA site coordinates; synthetic outcome = climate part + a smooth spatial field (random Fourier features, ~1000 km
scale) + noise; OLS-TP and XGB pooled out-of-fold r2 (oof_predict of mshi.analysis.transfer) under the kNNDM split
with Greenland in the domain (as the stage builds it) and without it (as aoa.ice_sheets excludes it)."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.analysis import knndm as kn
cfg = load_config()
K = cfg["phase2"]["within"]["knndm"]; spec = T.Spec.from_cfg(cfg)
g = pd.read_parquet("ne_grid_0p5.parquet")
d = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet").sort_values("site_id", kind="mergesort")
sub = d[d.continent_geo == "North America"][["site_id", "lon", "lat", "continent_geo"]].reset_index(drop=True)
x = np.c_[sub.lon, sub.lat]
splits = {}
for lab, grid in [("with Greenland", g), ("without Greenland", g[~g.subunit.eq("Greenland")])]:
    dom = T.prediction_domain(grid, "North America", K)
    f, info = kn.knndm_folds(x, dom, **{k: v for k, v in K.items() if k not in T.DOMAIN_KEYS}, earth_radius_km=6371.0)
    splits[lab] = (T.fold_pairs((f, info), len(sub))[0], info)
for rep in range(5):
    rng = np.random.default_rng(100 + rep)
    s = sub.copy(); n = len(s)
    s["bio01"] = 28 - 0.45 * s.lat.abs() + rng.normal(0, 2.0, n)
    s["bio12"] = np.exp(rng.normal(6.6, 0.5, n))
    for c in ("bio04", "bio05", "bio06", "bio14", "bio15", "bio17"):
        s[c] = rng.normal(50, 10, n)
    # smooth spatial field: random Fourier features on the unit sphere, length scale ~ 1000 km
    xyz = np.c_[np.cos(np.radians(s.lat)) * np.cos(np.radians(s.lon)), np.cos(np.radians(s.lat)) * np.sin(np.radians(s.lon)), np.sin(np.radians(s.lat))]
    Wf = rng.normal(0, 6371.0 / 1000.0, (200, 3)); b = rng.uniform(0, 2 * np.pi, 200)
    field = np.sqrt(2 / 200) * np.cos(xyz @ Wf.T + b) @ rng.normal(0, 1, 200)
    s["log_rs"] = 4.5 + 0.07 * s.bio01 + 0.35 * np.log(s.bio12) + 0.3 * field + rng.normal(0, 0.2, n)
    out = []
    for lab, (pairs, info) in splits.items():
        for learner in ("OLS-TP",):
            p, base, fold, _ = T.oof_predict(spec, learner, s, pairs)
            out.append(f"{lab}: q={info['q']} r2={T.r2(s.log_rs, p):.3f}")
    print(f"rep {rep}: " + " | ".join(out))
