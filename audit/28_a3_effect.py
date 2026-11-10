"""28_a3_effect.py - Analysis 3: how many SRDB records are in the wrong place, and does it matter?

Part 1 (tables): flagged-record table from 22_country_check.py with proposed fixes and confidence;
  class counts for (a) all records with coordinates, (b) records with Rs_annual, (c) records that pass
  every other Step 0 rule (i.e. would have entered the models); how many flagged records fell inside
  the original study's rectangles ("Asia" 25-180E, 10S-80N; "US" 125-66W, 24-50N).
Part 2 (effect): rebuild the site table with flagged records (i) as-is, (ii) excluded (Step 0
  default), (iii) corrected (high/medium-confidence fixes applied, others excluded), and rerun the
  Analysis 1 transfer pairs among the training continents (Asia, North America, Europe) with the same
  models, tuning, seeds and bootstrap. Reports each metric per policy and the change vs 'excluded'.

Usage: python -I audit/28_a3_effect.py
Outputs (audit/outputs/a3/): flagged_records.csv, class_counts.csv, box_contamination.json,
  effect_<v>.csv, effect_delta_<v>.csv
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402
import mshi_sites as S  # noqa: E402

OUTD = C.OUT / "a3"
OUTD.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("a1t", Path(__file__).resolve().parent / "24_a1_transfer.py")
A1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A1)

TRAIN = ["Asia", "North America", "Europe"]


def in_asia_box(lat, lon):
    return (lon >= 25) & (lon <= 180) & (lat >= -10) & (lat <= 80)


def in_us_box(lat, lon):
    return (lon >= -125) & (lon <= -66) & (lat >= 24) & (lat <= 50)


def part1():
    chk = pd.read_csv(C.OUT / "srdb_country_check.csv")
    d = C.load_srdb()
    d["qset"] = d["Quality_flag"].map(C.parse_qflags)
    other_ok = (d["Rs_annual"].notna() & (d["Manipulation"].isna() | (d["Manipulation"] == "None"))
                & d["Rs_annual"].between(C.RS_MIN, C.RS_MAX) & ~d["qset"].map(lambda s: bool(s & C.BAD_QFLAGS))
                & d["Duplicate_record"].isna() & (d["Annual_coverage"].isna() | (d["Annual_coverage"] >= 1)))
    chk["passes_other_step0_rules"] = chk["Record_number"].map(dict(zip(d["Record_number"], other_ok)))
    mm = chk[chk["status"] == "mismatch"].copy()
    mm["original_in_asia_box"] = in_asia_box(mm["Latitude"], mm["Longitude"])
    mm["original_in_us_box"] = in_us_box(mm["Latitude"], mm["Longitude"])
    cols = ["Record_number", "Study_number", "Country", "Region", "Site_name", "Latitude", "Longitude",
            "unit_name", "continent_at_coords", "mismatch_class", "confidence", "fix_lat", "fix_lon", "fix_country",
            "fix_continent", "evidence", "corroborated_by", "dist_to_stated_km", "Rs_annual",
            "passes_other_step0_rules", "original_in_asia_box", "original_in_us_box"]
    mm[cols].sort_values(["confidence", "mismatch_class", "Study_number", "Record_number"]).to_csv(
        OUTD / "flagged_records.csv", index=False)
    rows = []
    for scope, m in [("all records with coordinates", mm), ("records with Rs_annual", mm[mm["Rs_annual"].notna()]),
                     ("records passing all other Step 0 rules", mm[mm["passes_other_step0_rules"] == True])]:  # noqa: E712
        vc = m.groupby(["mismatch_class", "confidence"]).size().rename("n").reset_index()
        for _, r in vc.iterrows():
            rows.append({"scope": scope, "mismatch_class": r["mismatch_class"], "confidence": r["confidence"],
                         "n_records": int(r["n"]),
                         "n_studies": int(m[(m["mismatch_class"] == r["mismatch_class"]) & (m["confidence"] == r["confidence"])]["Study_number"].nunique())})
        rows.append({"scope": scope, "mismatch_class": "TOTAL", "confidence": "all", "n_records": int(len(m)),
                     "n_studies": int(m["Study_number"].nunique())})
    cc = pd.DataFrame(rows)
    cc.to_csv(OUTD / "class_counts.csv", index=False)
    ok = mm[mm["passes_other_step0_rules"] == True]  # noqa: E712
    box = {
        "flagged_passing_other_rules": int(len(ok)),
        "of_which_original_coords_in_asia_box": int(ok["original_in_asia_box"].sum()),
        "of_which_in_asia_box_but_stated_country_outside_asia": int((ok["original_in_asia_box"] & ok["fix_continent"].notna() & (ok["fix_continent"] != "Asia")).sum()),
        "of_which_original_coords_in_us_box": int(ok["original_in_us_box"].sum()),
        "records_in_asia_box_listing": ok[ok["original_in_asia_box"]][["Record_number", "Country", "Latitude", "Longitude", "mismatch_class", "confidence"]].to_dict("records"),
        "records_in_us_box_listing": ok[ok["original_in_us_box"]][["Record_number", "Country", "Latitude", "Longitude", "mismatch_class", "confidence"]].to_dict("records"),
        "n_checked": int(len(chk)), "n_flagged": int(len(mm)), "share_flagged": float(len(mm) / len(chk)),
    }
    C.write_json(box, OUTD / "box_contamination.json")
    print(cc.to_string())
    print({k: v for k, v in box.items() if not k.endswith("listing")})


def build_sites(policy: str, variant: str):
    srdb, steps, _ = S.srdb_records(policy)
    cos, _ = S.cosore_records()
    rec = pd.concat([srdb, cos.astype(srdb.dtypes.to_dict(), errors="ignore")], ignore_index=True)
    rec = S.add_continent(rec)
    rec = rec[~rec["continent"].isin(["Sea", "Other"])]
    rec = S.add_worldclim(rec)
    rec = rec[rec[C.BIO_COLS].notna().all(axis=1)]
    if variant == "strict":
        rec = rec[~rec["cov_missing"]]
    sites = S.aggregate_sites(rec)
    n_flag_sites = int(sites["record_ids"].str.split(";").map(
        lambda ids: any(i in FLAGGED_IDS for i in ids)).sum())
    return sites, steps[-1], n_flag_sites


def part2():
    global FLAGGED_IDS
    chk = pd.read_csv(C.OUT / "srdb_country_check.csv")
    FLAGGED_IDS = set("srdb_" + chk.loc[chk["status"] == "mismatch", "Record_number"].astype(int).astype(str))
    for v in ["strict", "incl_missing"]:
        rows, prow, meta = [], [], {}
        fixed = {}  # XGBoost hyperparameters tuned under the 'exclude' policy, reused for xgb_fixed
        for policy in ["exclude", "asis", "corrected"]:
            sites, last_step, nfs = build_sites(policy, v)
            meta[policy] = {"last_step": last_step, "sites_with_flagged_records": nfs,
                            "sites_by_continent": sites["continent"].value_counts().to_dict(), "xgb": {}}
            for T in TRAIN:
                tr = sites[sites["continent"] == T]
                names = [E for E in TRAIN if E != T]
                tests = [sites[sites["continent"] == E] for E in names]
                preds, info = A1.fit_predict_all(tr, tests)
                meta[policy]["xgb"][T] = {"params": info["xgb_params"], "n_estimators": info["xgb_n_estimators"]}
                if policy == "exclude":
                    fixed[T] = (info["xgb_params"], info["xgb_n_estimators"])
                # same hyperparameters for every policy -> isolates the data effect from re-tuning
                fx, _ = C.xgb_seed_predictions(tr[C.BIO_COLS].values, tr["log_rs"].values,
                                               [t[C.BIO_COLS].values for t in tests], *fixed[T])
                for j, (E, te) in enumerate(zip(names, tests)):
                    pm = {m: preds[m][j] for m in A1.MODELS}
                    tag = {"variant": v, "policy": policy, "train": T, "test": E, "n_train": len(tr),
                           "n_test": len(te), "kind": "transfer"}
                    A1.evaluate(te["log_rs"].values, pm, tag, rows, prow)
                    bm = C.boot_metrics(te["log_rs"].values, fx[j], idx=C.boot_idx(len(te)))
                    r = {**tag, "model": "xgb_fixed"}
                    for k in ["r2", "rmse_g", "mae_g", "bias_g", "bias_log", "spearman"]:
                        r[k], r[k + "_lo"], r[k + "_hi"], r[k + "_seed_sd"] = (bm[k]["est"], bm[k]["lo"],
                                                                               bm[k]["hi"], bm[k]["seed_sd"])
                    rows.append(r)
            print(v, policy, meta[policy], flush=True)
        res = pd.DataFrame(rows)
        res.to_csv(OUTD / f"effect_{v}.csv", index=False)
        base = res[res["policy"] == "exclude"].set_index(["train", "test", "model"])
        drows = []
        for policy in ["asis", "corrected"]:
            p = res[res["policy"] == policy].set_index(["train", "test", "model"])
            for k in p.index:
                r = {"variant": v, "policy": policy, "train": k[0], "test": k[1], "model": k[2],
                     "n_train": p.loc[k, "n_train"], "n_test": p.loc[k, "n_test"],
                     "n_train_exclude": base.loc[k, "n_train"], "n_test_exclude": base.loc[k, "n_test"]}
                for m in ["r2", "rmse_g", "mae_g", "bias_g", "spearman"]:
                    r[f"d_{m}"] = p.loc[k, m] - base.loc[k, m]
                drows.append(r)
        dd = pd.DataFrame(drows)
        dd.to_csv(OUTD / f"effect_delta_{v}.csv", index=False)
        C.write_json(meta, OUTD / f"effect_meta_{v}.json")
        print(dd[dd["model"].isin(["ols_P", "xgb"])].round(3).to_string(), flush=True)
        print("max |d_r2|:", dd["d_r2"].abs().max(), "max |d_rmse_g|:", dd["d_rmse_g"].abs().max(), flush=True)


FLAGGED_IDS: set = set()

if __name__ == "__main__":
    part1()
    part2()
