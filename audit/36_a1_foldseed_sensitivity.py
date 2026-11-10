"""36_a1_foldseed_sensitivity.py - how much do the within-continent spatial-block CV R2 values in
Analysis 1 depend on the random assignment of 5-degree blocks to folds?

Repeats the nested within-continent block CV of 24_a1_transfer.py (same models, same grid, inner
tuning on outer-training sites only) with outer fold seeds 42..46. To keep run time reasonable each
XGBoost fit uses 5 seeds (42..46) instead of 20; the seed-42 fold result is therefore close to, but
not identical with, the value in transfer_<v>.csv. Reports R2 per fold seed and the range.

Usage: python -I audit/36_a1_foldseed_sensitivity.py
Output: audit/outputs/a1/foldseed_sensitivity_<v>.csv, foldseed_summary_<v>.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

OUTD = C.OUT / "a1"
FOLD_SEEDS = [42, 43, 44, 45, 46]
XGB_SEEDS = 5
WITHIN_MIN_SITES = 50


def main() -> int:
    for v in ["strict", "incl_missing"]:
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        sites = sites[sites["continent"].isin(C.CONTINENT_ORDER)].reset_index(drop=True)
        counts = sites["continent"].value_counts()
        rows = []
        for E in [c for c in C.CONTINENT_ORDER if counts.get(c, 0) >= WITHIN_MIN_SITES]:
            d = sites[sites["continent"] == E].reset_index(drop=True)
            y = d["log_rs"].values
            for fs in FOLD_SEEDS:
                folds = C.block_folds(d["lat"].values, d["lon"].values, seed=fs)
                oof = {m: np.full(len(d), np.nan) for m in ["baseline", "ols_P", "ols_TP", "xgb"]}
                for f in range(C.N_FOLDS):
                    trm, tem = folds != f, folds == f
                    tr, te = d[trm], d[tem]
                    oof["baseline"][tem] = tr["log_rs"].mean()
                    oof["ols_P"][tem] = C.ols_fit_predict(tr[["log_bio12"]].values, tr["log_rs"].values,
                                                          te[["log_bio12"]].values)[0]
                    oof["ols_TP"][tem] = C.ols_fit_predict(tr[["bio1", "log_bio12"]].values, tr["log_rs"].values,
                                                           te[["bio1", "log_bio12"]].values)[0]
                    inner = C.block_folds(tr["lat"].values, tr["lon"].values)
                    params, n_est, _ = C.xgb_tune(tr[C.BIO_COLS].values, tr["log_rs"].values, inner)
                    outs, _ = C.xgb_seed_predictions(tr[C.BIO_COLS].values, tr["log_rs"].values, [te[C.BIO_COLS].values],
                                                     params, n_est, n_seeds=XGB_SEEDS)
                    oof["xgb"][tem] = outs[0].mean(axis=0)
                for m, p in oof.items():
                    rows.append({"variant": v, "continent": E, "n_sites": len(d), "fold_seed": fs, "model": m,
                                 "r2": float(C.r2(y, p))})
                print(v, E, fs, {m: round(float(C.r2(y, p)), 3) for m, p in oof.items()}, flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(OUTD / f"foldseed_sensitivity_{v}.csv", index=False)
        summ = df.groupby(["continent", "model"])["r2"].agg(["mean", "min", "max", "std"]).reset_index()
        summ.to_csv(OUTD / f"foldseed_summary_{v}.csv", index=False)
        print(summ.round(3).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
