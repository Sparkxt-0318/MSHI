"""24_a1_transfer.py - Analysis 1: continent-by-continent transfer matrix, climate predictors only.

Question: is the weak, one-directional Asia -> North America transfer a general pattern or a one-off?

Train continents: >= 150 sites in the Step 0 table. Test continents: all six (>= 20 sites).
Models (identical test sites for every model):
  baseline   training-continent mean of log Rs
  ols_P      OLS on log annual precipitation (log bio12)
  ols_TP     OLS on mean annual temperature (bio1) + log bio12
  xgb        XGBoost on bio 1,4,5,6,12,14,15,17; hyperparameters chosen by 5-fold 5-degree spatial-block
             CV inside the training continent only (grid in mshi_common.XGB_GRID); final model refitted
             with 20 seeds (42..61); metrics are means over seeds.
Metrics: R2 (log scale, test-set SST), RMSE / MAE / bias in g C m-2 yr-1 (after exp), bias on the log
scale, Spearman rho. 95% intervals: 2000 bootstrap resamples of test sites (seed 42); for xgb each
resample's metric is the mean over the 20 seeds. Paired differences use the same resamples.
Within-continent reference: 5-fold 5-degree spatial-block CV (fold assignment seed 42) with nested
tuning for xgb (inner block CV on the outer-training sites only).

Usage: python -I audit/24_a1_transfer.py [strict|incl_missing ...]
Outputs (audit/outputs/a1/): transfer_<v>.csv, paired_<v>.csv, withincv_<v>.csv, predictions_<v>.parquet,
  tuning_<v>_<train>.csv, run_<v>.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

TRAIN_MIN_SITES = 150
TEST_MIN_SITES = 20
WITHIN_MIN_SITES = 50
MODELS = ["baseline", "ols_P", "ols_TP", "xgb"]
PAIRS = [("xgb", "baseline"), ("ols_P", "baseline"), ("ols_TP", "baseline"), ("xgb", "ols_P"),
         ("xgb", "ols_TP"), ("ols_TP", "ols_P")]
OUTD = C.OUT / "a1"
OUTD.mkdir(parents=True, exist_ok=True)


def fit_predict_all(tr: pd.DataFrame, tests: list[pd.DataFrame], tune_tag: str | None = None, log=None):
    """Fit the four models on `tr`, predict each frame in `tests`. Returns (preds, info);
    preds[model] = list of (S, n_test) arrays."""
    y = tr["log_rs"].values
    preds = {m: [] for m in MODELS}
    info = {}
    for t in tests:
        preds["baseline"].append(np.full((1, len(t)), y.mean()))
        p, b = C.ols_fit_predict(tr[["log_bio12"]].values, y, t[["log_bio12"]].values)
        preds["ols_P"].append(p[None, :])
        info["ols_P_coef"] = b.tolist()
        p, b = C.ols_fit_predict(tr[["bio1", "log_bio12"]].values, y, t[["bio1", "log_bio12"]].values)
        preds["ols_TP"].append(p[None, :])
        info["ols_TP_coef"] = b.tolist()
    folds = C.block_folds(tr["lat"].values, tr["lon"].values)
    t0 = time.time()
    params, n_est, tab = C.xgb_tune(tr[C.BIO_COLS].values, y, folds)
    info["xgb_params"], info["xgb_n_estimators"] = params, n_est
    info["xgb_cv_mse_best"] = float(tab["cv_mse"].iloc[0])
    info["tune_seconds"] = round(time.time() - t0, 1)
    if tune_tag:
        tab.to_csv(OUTD / f"tuning_{tune_tag}.csv", index=False)
    outs, imp = C.xgb_seed_predictions(tr[C.BIO_COLS].values, y, [t[C.BIO_COLS].values for t in tests],
                                       params, n_est)
    preds["xgb"] = outs
    info["xgb_gain_importance"] = dict(zip(C.BIO_COLS, imp.tolist()))
    return preds, info


def evaluate(obs, pm: dict, tag: dict, rows: list, prow: list):
    idx = C.boot_idx(len(obs))
    boots = {}
    for m in MODELS:
        bm = C.boot_metrics(obs, pm[m], idx=idx)
        boots[m] = bm
        r = {**tag, "model": m}
        for k in ["r2", "rmse_g", "mae_g", "bias_g", "bias_log", "spearman"]:
            r[k], r[k + "_lo"], r[k + "_hi"] = bm[k]["est"], bm[k]["lo"], bm[k]["hi"]
            r[k + "_seed_sd"] = bm[k]["seed_sd"]
        rows.append(r)
    for a, b in PAIRS:
        for k in ["r2", "rmse_g", "spearman"]:
            diff = boots[a][k + "_boot"] - boots[b][k + "_boot"]
            prow.append({**tag, "model_a": a, "model_b": b, "metric": k,
                         "diff": boots[a][k]["est"] - boots[b][k]["est"],
                         "lo": float(np.nanpercentile(diff, 2.5)), "hi": float(np.nanpercentile(diff, 97.5)),
                         "share_boot_a_better": float(np.nanmean(diff > 0) if k != "rmse_g" else np.nanmean(diff < 0))})


def run_variant(v: str) -> None:
    t_start = time.time()
    sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
    sites = sites[sites["continent"].isin(C.CONTINENT_ORDER)].reset_index(drop=True)
    counts = sites["continent"].value_counts()
    train_c = [c for c in C.CONTINENT_ORDER if counts.get(c, 0) >= TRAIN_MIN_SITES]
    test_c = [c for c in C.CONTINENT_ORDER if counts.get(c, 0) >= TEST_MIN_SITES]
    rows, prow, pred_rows, run = [], [], [], {"variant": v, "counts": counts.to_dict(), "train": train_c,
                                               "test": test_c, "versions": C.versions(), "fits": {}}
    print(f"[{v}] counts {counts.to_dict()}", flush=True)
    for T in train_c:
        tr = sites[sites["continent"] == T]
        tests = [sites[sites["continent"] == E] for E in test_c if E != T]
        names = [E for E in test_c if E != T]
        preds, info = fit_predict_all(tr, tests, tune_tag=f"{v}_{C.CONT_ABBR[T]}")
        run["fits"][T] = info
        print(f"[{v}] train {T} n={len(tr)} xgb {info['xgb_params']} n_est={info['xgb_n_estimators']} "
              f"cvMSE={info['xgb_cv_mse_best']:.3f} ({info['tune_seconds']} s)", flush=True)
        for j, (E, te) in enumerate(zip(names, tests)):
            pm = {m: preds[m][j] for m in MODELS}
            tag = {"variant": v, "train": T, "test": E, "n_train": len(tr), "n_test": len(te), "kind": "transfer"}
            evaluate(te["log_rs"].values, pm, tag, rows, prow)
            for m in MODELS:
                pred_rows.append(pd.DataFrame({"variant": v, "kind": "transfer", "train": T, "test": E, "model": m,
                                               "cell": te["cell"].values, "obs": te["log_rs"].values,
                                               "pred": pm[m].mean(axis=0), "pred_seed_sd": pm[m].std(axis=0)}))
    # ---- within-continent spatial-block CV (reference) ----
    for E in [c for c in C.CONTINENT_ORDER if counts.get(c, 0) >= WITHIN_MIN_SITES]:
        d = sites[sites["continent"] == E].reset_index(drop=True)
        folds = C.block_folds(d["lat"].values, d["lon"].values)
        oof = {m: np.full((C.N_SEEDS if m == "xgb" else 1, len(d)), np.nan) for m in MODELS}
        fold_info = []
        for f in range(C.N_FOLDS):
            trm, tem = folds != f, folds == f
            preds, info = fit_predict_all(d[trm], [d[tem]])
            for m in MODELS:
                oof[m][:, tem] = preds[m][0]
            fold_info.append({"fold": f, "n_train": int(trm.sum()), "n_test": int(tem.sum()),
                              "xgb_params": info["xgb_params"], "n_est": info["xgb_n_estimators"]})
        run.setdefault("within", {})[E] = fold_info
        tag = {"variant": v, "train": E, "test": E, "n_train": len(d), "n_test": len(d), "kind": "within_blockcv"}
        evaluate(d["log_rs"].values, oof, tag, rows, prow)
        for m in MODELS:
            pred_rows.append(pd.DataFrame({"variant": v, "kind": "within_blockcv", "train": E, "test": E, "model": m,
                                           "cell": d["cell"].values, "obs": d["log_rs"].values,
                                           "pred": oof[m].mean(axis=0), "pred_seed_sd": oof[m].std(axis=0)}))
        print(f"[{v}] within {E} done", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(OUTD / f"transfer_{v}.csv", index=False)
    pd.DataFrame(prow).to_csv(OUTD / f"paired_{v}.csv", index=False)
    pd.concat(pred_rows, ignore_index=True).to_parquet(OUTD / f"predictions_{v}.parquet", index=False)
    run["seconds"] = round(time.time() - t_start, 1)
    C.write_json(run, OUTD / f"run_{v}.json")
    show = res[res["model"].isin(["ols_P", "xgb"])][["kind", "train", "test", "n_train", "n_test", "model", "r2",
                                                      "r2_lo", "r2_hi", "rmse_g", "spearman"]]
    print(show.round(3).to_string(), flush=True)


if __name__ == "__main__":
    for v in (sys.argv[1:] or ["strict", "incl_missing"]):
        run_variant(v)
