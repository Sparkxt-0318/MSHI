"""26_a1_modis.py - Analysis 1 secondary run: Asia <-> North America with MODIS NPP added, to connect
with the original study (climate + NPP). Same tuning, seeds and bootstrap as 24_a1_transfer.py, on the
subset of sites that have an NPP value. The raster's bounding box is lon -125..180, lat -39.2..87.8,
but its data footprint is much smaller (review finding): every column from 66 W to 25 E is empty, and
North America has no data north of about 51-54 N, so boreal Canadian sites drop out as well as those
west of 125 W. Drops are logged by cause, and the climate-only models are also scored on the full A1
test set so that the selection effect is visible. Every with/without-NPP comparison is on identical
sites and identical bootstrap resamples; numbers from this script must not be compared with
24_a1_transfer.py's, which use all sites.

Models: ols_TP (bio1 + log bio12), ols_TPN (+ log NPP), xgb (8 bioclim), xgb_npp (8 bioclim + NPP).
After independent review, the NPP effect for XGBoost is reported at MATCHED hyperparameters (primary):
  xgb_npp@xgb   = xgb_npp fitted with the hyperparameters tuned for xgb, compared with xgb
  xgb@xgb_npp   = xgb fitted with the hyperparameters tuned for xgb_npp, compared with xgb_npp
The separately tuned contrast (xgb_npp - xgb) is kept as secondary; it also contains the effect of
selecting different hyperparameters.
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
import mshi_sites as S  # noqa: E402

OUTD = C.OUT / "a1"
PAIRS = [("Asia", "North America"), ("North America", "Asia")]
FEATS_NPP = C.BIO_COLS + ["npp"]


def main() -> int:
    for v in ["strict", "incl_missing"]:
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        both = sites[sites["continent"].isin(["Asia", "North America"])]
        drop = both[both["npp"].isna()]
        s = both[both["npp"].notna()].copy()
        s["log_npp"] = np.log(np.clip(s["npp"], 1.0, None))
        a, x0, y0, sx, sy = S._npp_array()
        empty_cols = ~np.isfinite(a).any(axis=0)
        col = np.floor((drop["cell_lon"].values - x0) / sx).astype(int)
        outside = (drop["cell_lon"] < x0) | (drop["cell_lat"] > y0) | (drop["cell_lat"] < y0 - a.shape[0] * sy)
        in_empty_band = ~outside & empty_cols[np.clip(col, 0, a.shape[1] - 1)]
        cause = np.where(outside, "outside raster bounding box (west of 125 W)",
                         np.where(in_empty_band, "inside bounding box, column empty (66 W-25 E band)",
                                  "inside footprint, pixel empty (north of the NA data edge, water/urban)"))
        drop = drop.assign(cause=cause)
        run = {"variant": v, "dropped_no_npp": drop.groupby("continent").size().to_dict(),
               "dropped_west_of_125W": int((drop["lon"] < -125).sum()),
               "dropped_by_cause": drop.groupby(["continent", "cause"]).size().rename("n").reset_index().to_dict("records"),
               "dropped_north_of_50N_in_NA": int(((drop["continent"] == "North America") & (drop["lat"] > 50)).sum()),
               "empty_raster_columns_lon_range": [float(x0 + sx * np.nonzero(empty_cols)[0].min()),
                                                  float(x0 + sx * (np.nonzero(empty_cols)[0].max() + 1))]
               if empty_cols.any() else None,
               "kept": s.groupby("continent").size().to_dict(), "fits": {}, "versions": C.versions()}
        # selection effect: the same climate-only OLS scored on all A1 test sites vs the NPP subset
        sel = []
        for T, E in PAIRS:
            trA, teA = both[both["continent"] == T], both[both["continent"] == E]
            pA, _ = C.ols_fit_predict(trA[["bio1", "log_bio12"]].values, trA["log_rs"].values, teA[["bio1", "log_bio12"]].values)
            sel.append({"train": T, "test": E, "model": "ols_TP", "sites": "all A1 sites", "n_train": len(trA),
                        "n_test": len(teA), "r2": float(C.r2(teA["log_rs"].values, pA))})
        run["selection_effect"] = sel
        rows, prow = [], []
        for T, E in PAIRS:
            tr, te = s[s["continent"] == T], s[s["continent"] == E]
            y = tr["log_rs"].values
            preds = {}
            p, _ = C.ols_fit_predict(tr[["bio1", "log_bio12"]].values, y, te[["bio1", "log_bio12"]].values)
            preds["ols_TP"] = p[None, :]
            p, _ = C.ols_fit_predict(tr[["bio1", "log_bio12", "log_npp"]].values, y,
                                     te[["bio1", "log_bio12", "log_npp"]].values)
            preds["ols_TPN"] = p[None, :]
            folds = C.block_folds(tr["lat"].values, tr["lon"].values)
            tuned = {}
            for name, feats in [("xgb", C.BIO_COLS), ("xgb_npp", FEATS_NPP)]:
                params, n_est, tab = C.xgb_tune(tr[feats].values, y, folds)
                tuned[name] = (params, n_est)
                outs, imp = C.xgb_seed_predictions(tr[feats].values, y, [te[feats].values], params, n_est)
                preds[name] = outs[0]
                run["fits"][f"{T}->{E}:{name}"] = {"params": params, "n_estimators": n_est,
                                                   "cv_mse": float(tab["cv_mse"].iloc[0]),
                                                   "total_gain_share": dict(zip(feats, imp.tolist()))}
            # matched-hyperparameter fits
            outs, _ = C.xgb_seed_predictions(tr[FEATS_NPP].values, y, [te[FEATS_NPP].values], *tuned["xgb"])
            preds["xgb_npp@xgb"] = outs[0]
            outs, _ = C.xgb_seed_predictions(tr[C.BIO_COLS].values, y, [te[C.BIO_COLS].values], *tuned["xgb_npp"])
            preds["xgb@xgb_npp"] = outs[0]
            obs = te["log_rs"].values
            idx = C.boot_idx(len(obs))
            boots = {}
            for m, P in preds.items():
                bm = C.boot_metrics(obs, P, idx=idx)
                boots[m] = bm
                r = {"variant": v, "train": T, "test": E, "n_train": len(tr), "n_test": len(te), "model": m}
                for k in ["r2", "rmse_g", "mae_g", "bias_g", "bias_log", "spearman"]:
                    r[k], r[k + "_lo"], r[k + "_hi"], r[k + "_seed_sd"] = (bm[k]["est"], bm[k]["lo"], bm[k]["hi"],
                                                                           bm[k]["seed_sd"])
                rows.append(r)
            for a, bb, role in [("xgb_npp@xgb", "xgb", "primary: NPP effect at xgb's hyperparameters"),
                                ("xgb_npp", "xgb@xgb_npp", "primary: NPP effect at xgb_npp's hyperparameters"),
                                ("ols_TPN", "ols_TP", "primary: NPP effect, OLS"),
                                ("xgb_npp", "xgb", "secondary: separately tuned (includes tuning-selection effect)"),
                                ("xgb_npp", "ols_TPN", "model comparison")]:
                d = boots[a]["r2_boot"] - boots[bb]["r2_boot"]
                prow.append({"variant": v, "train": T, "test": E, "model_a": a, "model_b": bb, "metric": "r2",
                             "role": role, "diff": boots[a]["r2"]["est"] - boots[bb]["r2"]["est"],
                             "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5))})
        pd.DataFrame(rows).to_csv(OUTD / f"modis_{v}.csv", index=False)
        pd.DataFrame(prow).to_csv(OUTD / f"modis_paired_{v}.csv", index=False)
        C.write_json(run, OUTD / f"modis_run_{v}.json")
        print(v, run["dropped_no_npp"], run["dropped_west_of_125W"], run["kept"], flush=True)
        print(pd.DataFrame(rows)[["train", "test", "n_train", "n_test", "model", "r2", "r2_lo", "r2_hi"]].round(3).to_string(), flush=True)
        print(pd.DataFrame(prow).round(3).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
