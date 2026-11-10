"""32_a3_overlap.py - Analysis 3 novelty check against SRDB's own quality control.

1. SRDB's R/srdb_check.R coordinate rules at HEAD 02163a7: latitude/longitude bounds and
   Country == "USA" & Longitude > 0 & Region != "Guam". Count records each rule flags now.
2. SRDB issue #50 "Low-land records" (open since 2019-09-17; record numbers whose half-degree land
   fraction is < 5%; list copied verbatim from the issue body, retrieved 2026-11-10 with
   `gh api -X GET search/issues -f q='repo:bpbond/srdb is:issue "Low-land records"'`).
   Overlap with the records flagged by 22_country_check.py.
3. How many flagged records a land mask could catch at all (original point > 10 km from any Natural
   Earth land/map-unit polygon) versus records whose wrong coordinates fall on land in another
   country (detectable only by comparing the Country field with the coordinates).

Usage: python -I audit/32_a3_overlap.py
Output: audit/outputs/a3/overlap_srdb_qc.json, audit/outputs/a3/overlap_issue50.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

OUTD = C.OUT / "a3"
ISSUE50 = [426, 427, 428, 803, 1134, 1135, 1136, 1137, 1607, 1608, 1609, 1610, 1857, 1858, 1864, 2655, 4032,
           4033, 4034, 4035, 4036, 4037, 4708, 4709, 4710, 4711, 4712, 4713, 4714, 4715, 4716, 4717, 4718, 4719,
           4720, 4721, 4722, 4723, 4724, 4725, 4726, 4727, 5683, 5684, 5685, 5686, 5687, 5688, 5689, 5690, 5691,
           5698, 5699, 5700, 5701, 5702, 5703, 5704, 5705, 5900, 5901, 5902, 6603, 6604, 6605, 6606, 6607, 6608,
           6641, 6712, 6713, 6774, 6775, 6776, 6777, 6878, 6879, 6880, 6881, 7120]


def main() -> int:
    d = C.load_srdb()
    chk = pd.read_csv(C.OUT / "srdb_country_check.csv")
    out = {"srdb_commit": "02163a7"}
    # 1. SRDB's own rules
    lat, lon = d["Latitude"], d["Longitude"]
    out["srdb_rule_bounds_violations"] = int(((lat.abs() > 90) | (lon.abs() > 180)).sum())
    bad_usa = (d["Country"] == "USA") & (lon > 0) & (d["Region"].fillna("") != "Guam")
    out["srdb_rule_usa_positive_longitude"] = int(bad_usa.fillna(False).sum())
    # USA spelled differently escapes the rule
    us_variants = d["Country"].isin(["United States", "U.S", "Kansas", "Florida"]) & (lon > 0)
    out["usa_variant_spellings_with_positive_longitude"] = int(us_variants.fillna(False).sum())
    # 2. issue #50
    i50 = pd.DataFrame({"Record_number": ISSUE50})
    m = i50.merge(chk[["Record_number", "Country", "Latitude", "Longitude", "status", "mismatch_class", "confidence",
                       "unit_name", "dist_to_stated_km"]], on="Record_number", how="left")
    m["in_current_srdb"] = m["status"].notna()
    m.to_csv(OUTD / "overlap_issue50.csv", index=False)
    flagged = chk[chk["status"] == "mismatch"]
    out["issue50_n"] = len(ISSUE50)
    out["issue50_status_now"] = m["status"].fillna("record not found or no coordinates").value_counts().to_dict()
    out["issue50_flagged_by_country_check_classes"] = m.loc[m["status"] == "mismatch", "mismatch_class"].value_counts().to_dict()
    out["flagged_total"] = int(len(flagged))
    out["flagged_also_in_issue50"] = int(flagged["Record_number"].isin(ISSUE50).sum())
    out["flagged_not_in_issue50"] = int((~flagged["Record_number"].isin(ISSUE50)).sum())
    hi = flagged[flagged["confidence"] == "high"]
    out["high_conf_flagged"] = int(len(hi))
    out["high_conf_also_in_issue50"] = int(hi["Record_number"].isin(ISSUE50).sum())
    # 3. land-mask detectability of each flagged record (original point)
    loc = C.CountryLocator()
    on_land = []
    for r in flagged.itertuples(index=False):
        u = loc.unit_at(r.Latitude, r.Longitude)
        if u is None:
            nu, _ = loc.nearest_unit(r.Latitude, r.Longitude, C.TOL_KM)
            on_land.append(nu is not None)
        else:
            on_land.append(True)
    flagged = flagged.assign(original_on_land=on_land)
    out["flagged_original_point_in_sea_gt10km"] = int((~flagged["original_on_land"]).sum())
    out["flagged_original_point_on_land_other_country"] = int(flagged["original_on_land"].sum())
    out["high_conf_on_land_other_country"] = int(flagged.loc[flagged["confidence"] == "high", "original_on_land"].sum())
    out["by_class_on_land"] = flagged.groupby("mismatch_class")["original_on_land"].agg(["sum", "size"]).rename(
        columns={"sum": "on_land", "size": "n"}).to_dict("index")
    with_rs = flagged[flagged["Rs_annual"].notna()]
    out["flagged_with_rs_on_land_other_country"] = int(with_rs["original_on_land"].sum())
    out["flagged_with_rs_in_sea"] = int((~with_rs["original_on_land"]).sum())
    C.write_json(out, OUTD / "overlap_srdb_qc.json")
    for k, v in out.items():
        print(k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
