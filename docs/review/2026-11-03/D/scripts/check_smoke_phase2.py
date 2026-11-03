"""Robustness: the Phase-2 stages on a smoke-sized (50-site) subset, as `make smoke` would run them once the gridded
sources are reachable (smoke runs skip the gate). Upstream results are recorded stand-ins: a seeded 50-site subset
of the e2e sandbox's analysis site tables (as smoke_subset draws it), their features (from the e2e features tables),
the full records table, and the e2e sandbox's synthetic WorldClim rasters. Each stage is called directly.
"""
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")

if __name__ == "__main__":
    import numpy as np
    import pandas as pd
    from mshi.config import load_config
    from mshi.io import write_result, write_table
    from mshi.data.rasters import worldclim_path
    from test_robustness import sandbox

    D = Path(sys.argv[1])
    e2e = load_config(D / "e2e/v3_sandbox.yaml")
    base = load_config()
    tmp = D / "tmp/smoke50"
    if tmp.exists():
        shutil.rmtree(tmp)

    def edit(d):
        d["phase2"]["bootstrap"]["n"] = 100
        d["phase2"]["transfer"]["rf"].update(n_estimators=10, n_jobs=2)
        d["phase2"]["noise_ceiling"].update(n_boot=5, n_jobs=1)
        d["phase2"]["aoa"]["perm_repeats"] = 1
        d["phase2"]["us_r2"]["xgb_seed_spread"] = [0, 1]
        d["phase2"]["within"]["knndm"]["max_pred_points"] = 300

    sand = sandbox(base, tmp, edit=edit)
    n, seed = base["smoke"]["n_sites"], base["smoke"]["seed"]
    feats, sites = {}, {}
    for v in ("qc", "repo"):
        st = pd.read_parquet(e2e.path("derived", f"sites_analysis_{v}.parquet"))
        idx = np.sort(np.random.default_rng(seed).choice(len(st), size=n, replace=False))
        sites[v] = st.iloc[idx].reset_index(drop=True)
        fa = pd.read_parquet(e2e.path("interim", f"features_analysis_{v}.parquet")).set_index("site_id")
        feats[v] = fa.loc[sites[v].site_id].reset_index()
        print(v, "smoke subset by continent_geo:", sites[v].continent_geo.value_counts().to_dict())
    rec = pd.read_parquet(e2e.path("derived", "records_analysis.parquet"))
    outs = [write_table(rec, sand.path("derived", "records_analysis.parquet"))]
    outs += [write_table(sites[v], sand.path("derived", f"sites_analysis_{v}.parquet")) for v in ("qc", "repo")]
    write_result(sand, {"stand_in": True}, "build_sites_analysis.json", outputs=outs)
    fo = [write_table(feats[v], sand.path("interim", f"features_analysis_{v}.parquet")) for v in ("qc", "repo")]
    write_result(sand, {"stand_in": True}, "features_analysis.json", outputs=fo)
    tifs = []
    for i in range(1, 20):
        dst = worldclim_path(sand, i)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(worldclim_path(e2e, i), dst)
        tifs.append(dst)
    write_result(sand, {"stand_in": True}, "fetch_worldclim.json", outputs=tifs)
    shutil.copytree(e2e.path("raw", "naturalearth"), sand.path("raw", "naturalearth"))

    from mshi.analysis.noise_ceiling import noise_ceiling
    from mshi.analysis.transfer import transfer_matrix, within_continent
    from mshi.analysis.aoa import aoa_sensitivity
    from mshi.analysis.us_r2 import us_r2
    for name, f in (("noise_ceiling", noise_ceiling), ("transfer_matrix", transfer_matrix),
                    ("within_continent", within_continent), ("aoa_sensitivity", aoa_sensitivity), ("us_r2", us_r2)):
        try:
            out = f(sand)
            print(f"{name}: ok {str(out)[:200]}")
        except Exception as e:  # noqa: BLE001
            print(f"{name}: FAILED {type(e).__name__}: {str(e)[:300]}")
            traceback.print_exc(limit=4)
