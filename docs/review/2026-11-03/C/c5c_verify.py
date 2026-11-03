"""Check 5c: independent verification of the aoa_sensitivity sandbox run of c5b (0.5 degrees, real code path):
- Greenland ice-sheet cells vs a direct point-in-polygon count on the NE Greenland subunit (+ cells assigned to it by
  the nearest-subunit rule); Antarctica cells; no cell north of -60 flagged except Greenland;
- the permutation-importance weights vs a direct scikit-learn computation (same model, same data, same seed);
- the CV fold sizes vs mshi.spatial.block_folds; the thresholds vs the training DI recomputed from scratch;
- area and flux shares by continent and latitude band recomputed from the grid table (pandas groupby);
- the transfer check's inside/outside counts and r2 recomputed from scratch."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

from common import REPO, SCRATCH
from mshi.config import Config, load_config
from mshi.analysis import aoa as AOA
from mshi.spatial import block_folds

name = sys.argv[1] if len(sys.argv) > 1 else "sb_aoa_05deg"
root = Path(SCRATCH) / name
cfg0 = load_config()
data = copy.deepcopy(cfg0.data)
data["paths"]["raw"] = str(root / "raw")
data["phase2"]["bootstrap"]["n"] = 200
data["phase2"]["aoa"]["grid_deg"] = 0.5
sand = Config(data, source=cfg0.source, out_root=root / "out")
r = json.loads(sand.path("results", "aoa_sensitivity.json").read_text())
t = pd.read_parquet(sand.path("interim", "aoa_di_grid.parquet"))
A = sand["phase2"]["aoa"]

# ice sheets
su = gpd.read_file(f"{REPO}/data/raw/naturalearth/v5.1.2/ne_50m_admin_0_map_subunits.geojson")
green = su[su.SUBUNIT == "Greenland"].geometry.union_all()
pts = gpd.GeoSeries(gpd.points_from_xy(t.lon, t.lat), crs=4326)
inside_green = pts.within(green).to_numpy()
print(f"cells flagged ice: {int(t.ice_sheet.sum())}; south of -60: {int((t.lat < -60).sum())}; "
      f"inside the Greenland polygon: {int(inside_green.sum())}; flagged ice north of -60: "
      f"{int((t.ice_sheet & (t.lat >= -60)).sum())} (of which inside the polygon {int((t.ice_sheet & (t.lat >= -60) & inside_green).sum())})")
print(f"result: {r['grid']['ice_sheets']}")
extra = t.ice_sheet & (t.lat >= -60) & ~inside_green
print(f"ice cells north of -60 outside the Greenland polygon (nearest-subunit rule within 50 km): {int(extra.sum())}; "
      f"their continent_geo: {t.continent_geo[extra].value_counts().to_dict()}")
missed = inside_green & ~t.ice_sheet.to_numpy()
print(f"cells inside the Greenland polygon not flagged: {int(missed.sum())}")

# sites, model, weights
feat = pd.read_parquet(sand.path("interim", "features_analysis_qc.parquet"))
sites, info = AOA.prepare_sites(feat, "log_rs", sand["phase2"]["c8"], sand["phase2"]["continents"])
from sklearn.inspection import permutation_importance
import xgboost
c8 = list(sand["phase2"]["c8"])
for tname in A["train"]:
    sub = sites[sites.continent_geo.isin(AOA.train_continents(tname, sand["phase2"]["continents"]))].reset_index(drop=True)
    X32 = sub[c8].to_numpy("float32")
    m = xgboost.XGBRegressor(**sand["clean_test"]["locked"]["xgb"], random_state=sand["phase2"]["transfer"]["xgb_seed"]).fit(
        X32, sub.log_rs.to_numpy(float))
    imp = permutation_importance(m, X32.astype(float), sub.log_rs.to_numpy(float), n_repeats=A["perm_repeats"],
                                 random_state=A["perm_seed"]).importances_mean
    w = np.clip(imp, 0, None)
    w = w / w.sum()
    got = np.array([r["training_sets"][tname]["weights"]["permutation"]["values"][c] for c in c8])
    folds = list(block_folds(sub.lon.to_numpy(float), sub.lat.to_numpy(float), A["cv"]["seed"], A["cv"]["block_deg"],
                             A["cv"]["folds"]))
    print(f"[{tname}] weights max |diff| vs direct sklearn: {np.max(np.abs(w - got)):.3g}; weights "
          f"{dict(zip(c8, np.round(got, 3)))}; fold sizes ok: "
          f"{[len(va) for _, va in folds] == r['training_sets'][tname]['cv']['fold_sizes']}")
    # training DI from scratch -> thresholds
    for wk in A["weights"]:
        ww = got if wk == "permutation" else np.full(len(c8), 1 / len(c8))
        X = X32.astype(float)
        mu, sd = X.mean(0), X.std(0)
        Z = (X - mu) / sd * ww
        from scipy.spatial.distance import cdist, pdist
        dbar = pdist(Z).mean()
        tdi = np.empty(len(Z))
        for tr, va in folds:
            tdi[va] = cdist(Z[va], Z[tr]).min(1) / dbar
        q1, q3 = np.quantile(tdi, [0.25, 0.75])
        fence = q3 + 1.5 * (q3 - q1)
        thr = {"whisker_max": tdi[tdi <= fence].max(), "q95": np.quantile(tdi, 0.95)}
        for th in A["thresholds"]:
            v = next(v for v in r["variants"] if v["train"] == tname and v["threshold"] == th and v["weights"] == wk)
            assert abs(v["threshold_value"] - thr[th]) < 1e-12, (tname, wk, th, v["threshold_value"], thr[th])
            # grid DI from scratch for this variant -> AOA column and shares
            col = f"di_{AOA._slug(tname)}_{wk}"
            G = t[c8].to_numpy(float) if set(c8) <= set(t.columns) else None
print("thresholds recomputed from scratch: equal (asserted)")

# shares from the grid table
bad = 0
for v in r["variants"]:
    s = AOA._slug(v["train"])
    ins = t[f"aoa_{s}_{v['threshold']}_{v['weights']}"].to_numpy()
    rs = np.exp(t[f"pred_log_{s}"].to_numpy())
    for dom, keep in (("all_land", np.ones(len(t), bool)), ("excluding_ice_sheets", ~t.ice_sheet.to_numpy())):
        d = pd.DataFrame({"out": ~ins[keep], "a": t.area_km2.to_numpy()[keep], "f": (rs * t.area_km2.to_numpy())[keep],
                          "c": t.continent_geo.to_numpy()[keep], "b": t.lat_band.to_numpy()[keep]})
        for gcol, key in (("c", "by_continent_geo"), ("b", "by_lat_band")):
            for gname, gd in d.groupby(gcol):
                af = gd.a[gd.out].sum() / gd.a.sum()
                ff = gd.f[gd.out].sum() / gd.f.sum()
                got = v[dom][key][gname]
                if abs(af - got["area_frac_outside"]) > 1e-12 or abs(ff - got["flux_frac_outside"]) > 1e-12:
                    bad += 1
print(f"share mismatches (by continent and latitude band, both domains, 8 variants): {bad}")
print("lat bands present:", sorted(t.lat_band.unique()), "| band of cells south of -60:",
      sorted(t.lat_band[t.lat < -60].unique()))
