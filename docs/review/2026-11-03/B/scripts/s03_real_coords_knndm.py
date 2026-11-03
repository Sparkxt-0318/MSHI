"""kNNDM on the real analysis QC site coordinates (no outcomes used) with the Natural-Earth stand-in grid as the
prediction domain, exactly as within_continent calls it (prediction_domain with the configured K, knndm_folds with
the configured settings, fold_match of the 5-degree block splits). Then North America with the Greenland ice sheet
removed from the domain (as aoa.ice_sheets removes it from the mapped domain)."""
import sys, time, json
sys.path.insert(0, "/home/user/MSHI")
import numpy as np, pandas as pd
from mshi.config import load_config
from mshi.analysis import transfer as T
from mshi.analysis import knndm as kn
from mshi.spatial import block_folds
cfg = load_config()
W = cfg["phase2"]["within"]; K = W["knndm"]; Rkm = cfg["site_build"]["earth_radius_km"]
g = pd.read_parquet("ne_grid_0p5.parquet")
d = pd.read_parquet("/home/user/MSHI/data/derived/sites_analysis_qc.parquet")[["site_id", "lon", "lat", "continent_geo"]]
d = d.sort_values("site_id", kind="mergesort").reset_index(drop=True)

def run(c, grid, label):
    sub = d[d.continent_geo == c].reset_index(drop=True)
    dom = T.prediction_domain(grid, c, K)
    t0 = time.time()
    f, info = kn.knndm_folds(np.c_[sub.lon, sub.lat], dom, **{k: v for k, v in K.items() if k not in T.DOMAIN_KEYS}, earth_radius_km=Rkm)
    t = time.time() - t0
    bl = []
    for s in W["seeds"]:
        lab = T.fold_labels(list(block_folds(sub.lon.values, sub.lat.values, s, W["block_deg"], W["folds"])), len(sub))
        bl.append(kn.fold_match(np.c_[sub.lon, sub.lat], dom, lab, Rkm)["W"])
    print(f"{label:28s} n={len(sub)} q={info['q']} random={info['random_cv']} W={info['W']:.1f} W_random={info['W_random']:.1f} "
          f"W_blocks={[round(x,1) for x in bl]} Gij_med={info['Gij_median_km']:.0f} Gj_med={info['Gj_median_km']:.1f} "
          f"Gjstar_med={info['Gjstar_median_km']:.0f} sizes={info['fold_sizes']} ({t:.1f}s)")
    return f, info

out = {}
for c in ["Asia", "Europe", "North America"]:
    out[c] = run(c, g, c)
f_ng, i_ng = run("North America", g[~g.subunit.eq("Greenland")], "North America w/o Greenland")
f_g, i_g = out["North America"]
same = len(set(zip(f_g.tolist(), f_ng.tolist()))) == len(np.unique(f_g))
print("North America: same kNNDM partition with and without Greenland in the domain:", same)
# Gij distribution with and without Greenland
sub = d[d.continent_geo == "North America"].reset_index(drop=True)
for lab, grid in [("with", g), ("without", g[~g.subunit.eq("Greenland")])]:
    dom = T.prediction_domain(grid, "North America", K)
    gij = kn.nearest_km(np.c_[sub.lon, sub.lat], dom, Rkm)
    print(f"Gij {lab} Greenland: quantiles 50/75/90/95% = {np.quantile(gij,[.5,.75,.9,.95]).round(0).tolist()} km")
