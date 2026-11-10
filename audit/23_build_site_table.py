"""23_build_site_table.py - Step 0: one clean global site table from SRDB (@02163a7) and COSORE
(0.8.0), shared by all three analyses.

Rules, applied in this order (counts of records removed by each are written to step0_counts.json
and step0_summary.md):
  SRDB: Rs_annual reported; unmanipulated (Manipulation == "None" or missing, read with
  keep_default_na=False); coordinates present; Rs_annual in [50, 4500]; no quality flag Q10-Q14;
  not a known duplicate (Duplicate_record empty; added rule, see prep_log); annual coverage >= 1 or
  missing; Country field agrees with the coordinates (22_country_check.py; mismatches excluded).
  COSORE: full-year (12 months, >= 5 days each) dataset-years of untreated Rs ports; Rs in [50, 4500].
  Both: COSORE dataset-years that duplicate an SRDB record (same cell, overlapping year) dropped;
  continent from Natural Earth map units; WorldClim 2.1 30" bioclim 1,4,5,6,12,14,15,17
  (nearest valid pixel within 3 px); records with no climate value dropped.
Aggregation: one site per MODIS-aligned 0.05-degree cell = mean of log Rs over all records in the
cell; n_records and within-cell SD kept. Two variants:
  strict        annual coverage == 1 (records with missing coverage dropped)
  incl_missing  annual coverage == 1 or missing

Usage: python -I audit/23_build_site_table.py
Outputs (audit/outputs/): clean_records.csv, clean_sites_strict.csv/.parquet,
  clean_sites_incl_missing.csv/.parquet, step0_counts.json, step0_summary.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402
import mshi_sites as S  # noqa: E402


def continent_table(rec: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    order = C.CONTINENT_ORDER + sorted(set(sites["continent"].dropna()) - set(C.CONTINENT_ORDER))
    rows = []
    for c in order:
        r = rec[rec["continent"] == c]
        s = sites[sites["continent"] == c]
        if len(r) == 0 and len(s) == 0:
            continue
        rows.append({"continent": c, "records": len(r), "records_srdb": int((r["source"] == "srdb").sum()),
                     "records_cosore": int((r["source"] == "cosore").sum()), "studies": r["study_id"].nunique(),
                     "sites": len(s), "sites_with_2plus_records": int((s["n_records"] >= 2).sum()),
                     "sites_with_3plus_records": int((s["n_records"] >= 3).sum()),
                     "median_rs_gm": float(np.exp(s["log_rs"].median())) if len(s) else np.nan,
                     "var_log_rs_sites": float(s["log_rs"].var(ddof=1)) if len(s) > 1 else np.nan})
    t = pd.DataFrame(rows)
    tot = {"continent": "Total", "records": len(rec), "records_srdb": int((rec["source"] == "srdb").sum()),
           "records_cosore": int((rec["source"] == "cosore").sum()), "studies": rec["study_id"].nunique(),
           "sites": len(sites), "sites_with_2plus_records": int((sites["n_records"] >= 2).sum()),
           "sites_with_3plus_records": int((sites["n_records"] >= 3).sum()),
           "median_rs_gm": float(np.exp(sites["log_rs"].median())), "var_log_rs_sites": float(sites["log_rs"].var(ddof=1))}
    return pd.concat([t, pd.DataFrame([tot])], ignore_index=True)


def main() -> int:
    srdb, steps_s, marginal = S.srdb_records("exclude")
    cos, steps_c = S.cosore_records()
    rec = pd.concat([srdb, cos], ignore_index=True)
    steps_both = []
    n0 = len(rec)
    rec, dup_log = S.drop_cosore_duplicates(rec)
    S._step(steps_both, "COSORE dataset-year not already in SRDB (same cell, overlapping year)", n0, len(rec),
            note=f"{len(dup_log)} COSORE records dropped as duplicates of SRDB records")
    rec = S.add_continent(rec)
    n0 = len(rec)
    sea = rec["continent"].isin(["Sea", "Other"])
    rec = rec[~sea]
    S._step(steps_both, "record located on land or within 10 km of land (continent assigned)", n0, len(rec))
    rec = S.add_worldclim(rec)
    n0 = len(rec)
    miss = rec[C.BIO_COLS].isna().any(axis=1)
    n_offset = int((rec[[f"bio{b}_offset_px" for b in C.BIO]].fillna(0) > 0).any(axis=1).sum())
    rec = rec[~miss].copy()
    S._step(steps_both, "WorldClim value found within 3 pixels (~2.7 km)", n0, len(rec),
            note=f"{n_offset} records used a neighbouring pixel")
    rec.to_csv(C.OUT / "clean_records.csv", index=False)

    variants = {"strict": rec[~rec["cov_missing"]], "incl_missing": rec}
    out = {"created": C.now_utc(), "versions": C.versions(), "steps_srdb": steps_s, "steps_cosore": steps_c,
           "cosore_srdb_duplicates": dup_log,
           "steps_combined": steps_both, "marginal_counts_among_records_with_rs_annual": marginal,
           "variants": {}}
    md = ["# Step 0 site table: summary", "",
          f"Created {out['created']} by `audit/23_build_site_table.py`. SRDB commit 02163a7 (data update "
          "30 Dec 2025); COSORE 0.8.0 (git 02f32e8); WorldClim 2.1 30\" bioclim 1, 4, 5, 6, 12, 14, 15, 17; "
          "Natural Earth 1:10m map units.", "", "## Record filters (applied in order)", "",
          "| Source | Rule | Before | Removed | After |", "|---|---|---:|---:|---:|"]
    for src, st in [("SRDB", steps_s), ("COSORE", steps_c), ("Both", steps_both)]:
        for s in st:
            md.append(f"| {src} | {s['rule']}{(' (' + s['note'] + ')') if s['note'] else ''} | {s['n_before']} | {s['n_removed']} | {s['n_after']} |")
    md += ["", "Marginal counts (records with Rs_annual failing each rule on its own): " +
           "; ".join(f"{k}: {v}" for k, v in marginal.items()) + ".", ""]
    md += [f"Records with annual coverage missing kept in `incl_missing`: {int(rec['cov_missing'].sum())} "
           f"(SRDB). Records in `strict`: {int((~rec['cov_missing']).sum())}.", ""]
    for name, r in variants.items():
        sites = S.aggregate_sites(r)
        sites = S.add_npp(sites)
        sites.to_csv(C.OUT / f"clean_sites_{name}.csv", index=False)
        sites.to_parquet(C.OUT / f"clean_sites_{name}.parquet", index=False)
        ct = continent_table(r, sites)
        out["variants"][name] = {
            "n_records": int(len(r)), "n_sites": int(len(sites)),
            "share_cells_multi_record": float((sites["n_records"] > 1).mean()),
            "cells_spanning_two_continents": int((sites["n_continents_in_cell"] > 1).sum()),
            "sites_with_npp": int(sites["npp"].notna().sum()),
            "by_continent": ct.to_dict("records"),
        }
        md += [f"## Variant `{name}`: {len(r)} records, {len(sites)} sites (0.05-degree cells)", "",
               f"Share of cells with more than one record: {100 * (sites['n_records'] > 1).mean():.1f}%. "
               f"Cells whose records fall in two continents: {(sites['n_continents_in_cell'] > 1).sum()}. "
               f"Sites with a MODIS NPP value: {sites['npp'].notna().sum()}.", "",
               "| Continent | Records | SRDB | COSORE | Studies | Sites | Sites with 2+ records | 3+ | Median Rs (g C m-2 yr-1) | Var log Rs |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for _, x in ct.iterrows():
            md.append(f"| {x['continent']} | {x['records']} | {x['records_srdb']} | {x['records_cosore']} | "
                      f"{x['studies']} | {x['sites']} | {x['sites_with_2plus_records']} | {x['sites_with_3plus_records']} | "
                      f"{x['median_rs_gm']:.0f} | {x['var_log_rs_sites']:.3f} |")
        md.append("")
    md += ["Continents: Natural Earth CONTINENT field, with Central America, the Caribbean and South America "
           "grouped as South & Central America (UN subregions; includes Mexico), Russia east of 60 E assigned "
           "to Asia, Hawaii to Oceania and the Canary Islands to Africa.", ""]
    C.write_json(out, C.OUT / "step0_counts.json")
    (C.OUT / "step0_summary.md").write_text("\n".join(md))
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
