"""31_a1_tuning_sensitivity.py - how much do the Analysis 1 XGBoost transfer R2 values depend on
which hyperparameter configuration the spatial-block CV happens to select?

For each training continent, take the 10 best configurations from the tuning table written by
24_a1_transfer.py (same grid, same 5-degree block folds, training continent only), refit each with
20 seeds and record the transfer R2 on every other continent. Reports the range across the top-10
configurations and how far apart they were in CV MSE (all are within a hair of the optimum, so the
spread measures selection instability, not overfitting to the test set: the test continent plays no
part in choosing or ranking them).

Usage: python -I audit/31_a1_tuning_sensitivity.py
Output: audit/outputs/a1/tuning_sensitivity_<v>.csv and _summary_<v>.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

OUTD = C.OUT / "a1"
TOPK = 10


def main() -> int:
    for v in ["strict", "incl_missing"]:
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        sites = sites[sites["continent"].isin(C.CONTINENT_ORDER)]
        rows = []
        for T in ["Asia", "North America", "Europe"]:
            tab = pd.read_csv(OUTD / f"tuning_{v}_{C.CONT_ABBR[T]}.csv").head(TOPK)
            tr = sites[sites["continent"] == T]
            tests = {E: sites[sites["continent"] == E] for E in C.CONTINENT_ORDER if E != T}
            for rank, cfg in tab.reset_index(drop=True).iterrows():
                params = {"max_depth": int(cfg["max_depth"]), "learning_rate": float(cfg["learning_rate"]),
                          "min_child_weight": float(cfg["min_child_weight"]), "reg_lambda": float(cfg["reg_lambda"])}
                outs, _ = C.xgb_seed_predictions(tr[C.BIO_COLS].values, tr["log_rs"].values,
                                                 [t[C.BIO_COLS].values for t in tests.values()], params,
                                                 int(cfg["n_estimators"]))
                for (E, te), P in zip(tests.items(), outs):
                    r2s = [C.r2(te["log_rs"].values, P[s]) for s in range(P.shape[0])]
                    rows.append({"variant": v, "train": T, "test": E, "rank": rank + 1, **params,
                                 "n_estimators": int(cfg["n_estimators"]), "cv_mse": float(cfg["cv_mse"]),
                                 "r2_mean_over_seeds": float(np.mean(r2s))})
            print(v, T, "done", flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(OUTD / f"tuning_sensitivity_{v}.csv", index=False)
        summ = df.groupby(["train", "test"]).agg(
            r2_rank1=("r2_mean_over_seeds", "first"), r2_min=("r2_mean_over_seeds", "min"),
            r2_max=("r2_mean_over_seeds", "max"), r2_median=("r2_mean_over_seeds", "median"),
            cv_mse_best=("cv_mse", "min"), cv_mse_10th=("cv_mse", "max")).reset_index()
        summ["r2_range"] = summ["r2_max"] - summ["r2_min"]
        summ.to_csv(OUTD / f"tuning_sensitivity_summary_{v}.csv", index=False)
        print(summ.round(3).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
