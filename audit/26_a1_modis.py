"""26_a1_modis.py - Analysis 1 secondary run: Asia <-> North America with MODIS NPP added, to connect
with the original study (climate + NPP). Same models, tuning, seeds and bootstrap as 24_a1_transfer.py,
on the subset of sites that have an NPP value (the MODIS rasters cover lon -125..180, lat -39.2..87.8
only, so North American sites west of 125 W, e.g. Alaska and the Pacific coast, drop out).
Every comparison (with vs without NPP) is on identical sites.

Models: ols_TP (bio1 + log bio12), ols_TPN (+ log NPP), xgb (8 bioclim), xgb_npp (8 bioclim + NPP).
Usage: python -I audit/26_a1_modis.py
Outputs: audit/outputs/a1/modis_<v>.csv, modis_paired_<v>.csv, modis_run_<v>.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

OUTD = C.OUT / "a1"
PAIRS = [("Asia", "North America"), ("North America", "Asia")]
MODELS = ["ols_TP", "ols_TPN", "xgb", "xgb_npp"]
FEATS_NPP = C.BIO_COLS + ["npp"]


def main() -> int:
    for v in ["strict", "incl_missing"]:
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        both = sites[sites["continent"].isin(["Asia", "North America"])]
        drop = both[both["npp"].isna()]
        s = both[both["npp"].notna()].copy()
        s["log_npp"] = np.log(np.clip(s["npp"], 1.0, None))
        run = {"variant": v, "dropped_no_npp": drop.groupby("continent").size().to_dict(),
               "dropped_west_of_125W": int((drop["lon"] < -125).sum()),
               "kept": s.groupby("continent").size().to_dict(), "fits": {}}
        rows, prow = [], []
        for T, E in PAIRS:
            tr, te = s[s["continent"] == T], s[s["continent"] == E]
            y = tr["log_rs"].values
            preds = {}
            p, _ = C.ols_fit_predict(tr[["bio1", "log_bio12"]].values, y, te[["bio1", "log_bio12"]].values)
            preds["ols_TP"] = p[None, :]
            p, b = C.ols_fit_predict(tr[["bio1", "log_bio12", "log_npp"]].values, y,
                                     te[["bio1", "log_bio12", "log_npp"]].values)
            preds["ols_TPN"] = p[None, :]
            folds = C.block_folds(tr["lat"].values, tr["lon"].values)
            for name, feats in [("xgb", C.BIO_COLS), ("xgb_npp", FEATS_NPP)]:
                params, n_est, tab = C.xgb_tune(tr[feats].values, y, folds)
                outs, imp = C.xgb_seed_predictions(tr[feats].values, y, [te[feats].values], params, n_est)
                preds[name] = outs[0]
                run["fits"][f"{T}->{E}:{name}"] = {"params": params, "n_estimators": n_est,
                                                   "cv_mse": float(tab["cv_mse"].iloc[0]),
                                                   "gain_importance": dict(zip(feats, imp.tolist()))}
            obs = te["log_rs"].values
            idx = C.boot_idx(len(obs))
            boots = {}
            for m in MODELS:
                bm = C.boot_metrics(obs, preds[m], idx=idx)
                boots[m] = bm
                r = {"variant": v, "train": T, "test": E, "n_train": len(tr), "n_test": len(te), "model": m}
                for k in ["r2", "rmse_g", "mae_g", "bias_g", "bias_log", "spearman"]:
                    r[k], r[k + "_lo"], r[k + "_hi"], r[k + "_seed_sd"] = (bm[k]["est"], bm[k]["lo"], bm[k]["hi"],
                                                                           bm[k]["seed_sd"])
                rows.append(r)
            for a, bb in [("xgb_npp", "xgb"), ("ols_TPN", "ols_TP"), ("xgb_npp", "ols_TPN")]:
                d = boots[a]["r2_boot"] - boots[bb]["r2_boot"]
                prow.append({"variant": v, "train": T, "test": E, "model_a": a, "model_b": bb, "metric": "r2",
                             "diff": boots[a]["r2"]["est"] - boots[bb]["r2"]["est"],
                             "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5))})
        pd.DataFrame(rows).to_csv(OUTD / f"modis_{v}.csv", index=False)
        pd.DataFrame(prow).to_csv(OUTD / f"modis_paired_{v}.csv", index=False)
        C.write_json(run, OUTD / f"modis_run_{v}.json")
        print(v, run["dropped_no_npp"], run["dropped_west_of_125W"], run["kept"])
        print(pd.DataFrame(rows)[["train", "test", "n_train", "n_test", "model", "r2", "r2_lo", "r2_hi", "spearman"]].round(3).to_string())
        print(pd.DataFrame(prow).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
