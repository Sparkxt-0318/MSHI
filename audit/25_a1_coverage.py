"""25_a1_coverage.py - Analysis 1: does transfer skill track how well the test continent's climate
is covered by the training continent? Descriptive only (6-15 pairs): no significance tests.

Coverage measures per train -> test pair:
  share_T_in_range   share of test sites with bio1 (MAT) inside the training min-max
  share_P_in_range   same for bio12 (annual precipitation)
  share_TP_in_range  both at once
  DI (Meyer & Pebesma 2021, Methods Ecol Evol, doi 10.1111/2041-210X.13650): predictors standardised
    with training mean/SD and weighted by the training-continent XGBoost gain importance (mean over 20
    seeds); DI = distance to the nearest training site / mean pairwise distance among training sites.
    AOA threshold = upper whisker (boxplot.stats) of cross-validated training DIs, where each
    training site's nearest neighbour is searched only in other 5-degree spatial-block folds (as in
    CAST::trainDI with CV folds). Unweighted DI reported as a sensitivity.
Output: audit/outputs/a1/coverage_<v>.csv and a descriptive Spearman rho per skill/coverage pairing.

Usage: python -I audit/25_a1_coverage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist, pdist
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

OUTD = C.OUT / "a1"


def di_stats(tr: pd.DataFrame, te: pd.DataFrame, weights: np.ndarray):
    Xtr = tr[C.BIO_COLS].values.astype(float)
    Xte = te[C.BIO_COLS].values.astype(float)
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0, ddof=1)
    sd[sd == 0] = 1.0
    w = np.asarray(weights, float)
    Ztr = (Xtr - mu) / sd * w
    Zte = (Xte - mu) / sd * w
    dbar = pdist(Ztr).mean()
    d_te = cdist(Zte, Ztr).min(axis=1) / dbar
    folds = C.block_folds(tr["lat"].values, tr["lon"].values)
    D = cdist(Ztr, Ztr)
    di_tr = np.empty(len(Ztr))
    for i in range(len(Ztr)):
        other = folds != folds[i]
        di_tr[i] = D[i, other].min() / dbar
    q1, q3 = np.percentile(di_tr, [25, 75])
    upper = q3 + 1.5 * (q3 - q1)
    thr = di_tr[di_tr <= upper].max()
    return d_te, thr, di_tr


def main() -> int:
    out_all = []
    for v in ["strict", "incl_missing"]:
        f = OUTD / f"transfer_{v}.csv"
        if not f.exists():
            continue
        res = pd.read_csv(f)
        run = json.loads((OUTD / f"run_{v}.json").read_text())
        sites = pd.read_parquet(C.OUT / f"clean_sites_{v}.parquet")
        rows = []
        tr_pairs = res[res["kind"] == "transfer"][["train", "test"]].drop_duplicates()
        for T, E in tr_pairs.itertuples(index=False):
            tr, te = sites[sites["continent"] == T], sites[sites["continent"] == E]
            imp = np.array([run["fits"][T]["xgb_total_gain_share"][c] for c in C.BIO_COLS])
            imp_avg = np.array([run["fits"][T]["xgb_avg_gain_share"][c] for c in C.BIO_COLS])
            d_w, thr_w, _ = di_stats(tr, te, imp)
            d_a, thr_a, _ = di_stats(tr, te, imp_avg)
            d_u, thr_u, _ = di_stats(tr, te, np.ones(len(C.BIO_COLS)))
            inT = te["bio1"].between(tr["bio1"].min(), tr["bio1"].max())
            inP = te["bio12"].between(tr["bio12"].min(), tr["bio12"].max())
            row = {"variant": v, "train": T, "test": E, "n_train": len(tr), "n_test": len(te),
                   "share_T_in_range": float(inT.mean()), "share_P_in_range": float(inP.mean()),
                   "share_TP_in_range": float((inT & inP).mean()),
                   "di_weighted_mean": float(d_w.mean()), "di_weighted_median": float(np.median(d_w)),
                   "aoa_threshold_weighted": float(thr_w), "share_in_aoa_weighted": float((d_w <= thr_w).mean()),
                   "di_unweighted_mean": float(d_u.mean()), "aoa_threshold_unweighted": float(thr_u),
                   "share_in_aoa_unweighted": float((d_u <= thr_u).mean()),
                   "di_avggain_mean": float(d_a.mean()), "share_in_aoa_avggain": float((d_a <= thr_a).mean())}
            for m in ["ols_P", "ols_TP", "xgb"]:
                r = res[(res["kind"] == "transfer") & (res["train"] == T) & (res["test"] == E) & (res["model"] == m)].iloc[0]
                row[f"r2_{m}"], row[f"r2_{m}_lo"], row[f"r2_{m}_hi"] = r["r2"], r["r2_lo"], r["r2_hi"]
                row[f"spearman_{m}"] = r["spearman"]
            rows.append(row)
        cov = pd.DataFrame(rows)
        cov.to_csv(OUTD / f"coverage_{v}.csv", index=False)
        desc = {}
        for skill in ["r2_xgb", "r2_ols_P", "r2_ols_TP", "spearman_xgb"]:
            for c in ["share_TP_in_range", "share_in_aoa_weighted", "di_weighted_mean", "share_in_aoa_unweighted"]:
                rho = spearmanr(cov[skill], cov[c]).correlation
                desc[f"{skill}~{c}"] = float(rho)
        C.write_json({"variant": v, "n_pairs": len(cov), "spearman_rho_descriptive_no_test": desc},
                     OUTD / f"coverage_rho_{v}.json")
        out_all.append(cov)
        print(cov[["train", "test", "n_test", "share_TP_in_range", "share_in_aoa_weighted", "di_weighted_mean",
                   "share_in_aoa_unweighted", "r2_ols_P", "r2_xgb"]].round(3).to_string())
        print({k: round(x, 2) for k, x in desc.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
