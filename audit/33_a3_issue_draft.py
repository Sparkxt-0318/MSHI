"""33_a3_issue_draft.py - draft (NOT submitted) of a GitHub issue for bpbond/srdb listing the
high-confidence coordinate / country errors found by 22_country_check.py. The author reviews and
posts it; nothing is sent anywhere by this script.

Usage: python -I audit/33_a3_issue_draft.py
Output: audit/outputs/a3/srdb_issue_draft.md, audit/outputs/a3/srdb_issue_high_confidence.csv
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

spec = importlib.util.spec_from_file_location("cc", Path(__file__).resolve().parent / "22_country_check.py")
CC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CC)

OUTD = C.OUT / "a3"
WHY = {"lon_sign": "longitude sign flipped", "lat_sign": "latitude sign flipped", "swap": "latitude and longitude swapped",
       "label_wrong": "Country field does not match Region/coordinates", "same_site_conflict":
       "coordinates differ from other records of the same site in the same study"}


def main() -> int:
    fl = pd.read_csv(OUTD / "flagged_records.csv") if (OUTD / "flagged_records.csv").exists() else None
    chk = pd.read_csv(C.OUT / "srdb_country_check.csv")
    hi = chk[(chk["status"] == "mismatch") & (chk["confidence"] == "high")].copy()
    st = C.load_srdb_studies().set_index("Study_number")
    adm1 = CC.Admin1()
    a1 = []
    for r in hi.itertuples(index=False):
        la, lo = (r.fix_lat, r.fix_lon) if pd.notna(r.fix_lat) else (r.Latitude, r.Longitude)
        k = adm1.at(la, lo)
        a1.append(f"{adm1.a.iloc[k]['name']} ({adm1.a.iloc[k]['admin']})" if k is not None else "")
    hi["admin1_at_proposed"] = a1
    hi["study_title"] = hi["Study_number"].map(lambda s: str(st.loc[s, "Title"])[:90] if s in st.index else "")
    hi["study_doi"] = hi["Study_number"].map(lambda s: st.loc[s, "DOI"] if s in st.index and isinstance(st.loc[s, "DOI"], str) else "")
    hi = hi.sort_values(["Study_number", "Record_number"])
    hi.to_csv(OUTD / "srdb_issue_high_confidence.csv", index=False)
    ov = json.loads((OUTD / "overlap_srdb_qc.json").read_text())
    summ = json.loads((C.OUT / "srdb_country_check_summary.json").read_text())

    lines = [
        "**Title:** Coordinate / Country inconsistencies in srdb-data.csv: "
        f"{len(hi)} high-confidence records in {hi['Study_number'].nunique()} studies",
        "",
        "Hello, and thanks for maintaining SRDB. While building a site table from `srdb-data.csv` at commit "
        "02163a7 (data update 30 Dec 2025), I compared each record's `Country` field with the country its "
        "`Latitude`/`Longitude` fall in (Natural Earth 1:10m admin-0 map units and admin-1 provinces; country "
        "names normalised for spelling variants such as \"USA\"/\"United States\", trailing spaces, \"Isreal\").",
        "",
        f"Of {summ['n_checked']} records with coordinates, {summ['status_counts'].get('mismatch', 0)} disagree with "
        "their Country field by more than 10 km. The records below are the ones where the fix is clear: flipping "
        "a sign or swapping latitude/longitude puts the point in the stated country (and usually in the stated "
        "Region), the Region field names the province the point actually lies in, or other records of the same "
        "site in the same study have consistent coordinates. None of them is caught by the USA-longitude check in "
        "`R/srdb_check.R`, and none is in the 'Low-land records' list of issue #50 "
        f"(only {ov['flagged_also_in_issue50']} of the {ov['flagged_total']} mismatches are; most wrong points fall on land "
        "in another country, so a land mask cannot catch them).",
        "",
        "Please treat the proposed values as suggestions to check against the original papers; I have not "
        "verified each one against the publication.",
        "",
        "| Record | Study | Country | Region / site | Lat, Lon in SRDB | Falls in | Problem | Proposed | Province at proposed point |",
        "|---:|---:|---|---|---|---|---|---|---|",
    ]
    for r in hi.itertuples(index=False):
        if r.mismatch_class == "label_wrong":
            prop = f"Country = {r.fix_country}"
        else:
            prop = f"{r.fix_lat:.6g}, {r.fix_lon:.6g}"
        site = " / ".join(str(x) for x in [r.Region, r.Site_name] if isinstance(x, str) and x)
        lines.append(f"| {int(r.Record_number)} | {int(r.Study_number)} | {r.Country} | {site} | "
                     f"{r.Latitude:.6g}, {r.Longitude:.6g} | {r.unit_name if isinstance(r.unit_name, str) else 'sea (> 10 km offshore)'} | {WHY.get(r.mismatch_class, r.mismatch_class)} | "
                     f"{prop} | {r.admin1_at_proposed} |")
    if 4564 in set(hi["Study_number"].astype(int)):
        lines += ["", "Study 4564: closed issue #132 corrected the UK site of this study. Record 1543 (Mols, Denmark) "
                      "still has 53.05, 3.47 (North Sea, the UK site's latitude), while record 1546 of the same study "
                      "and site has 56.38, 10.95; the #132 fix may have been applied to the wrong row."]
    lines += [
        "",
        "Study references (from `srdb-studies.csv`):",
        "",
    ]
    for s, g in hi.groupby("Study_number"):
        doi = g["study_doi"].iloc[0]
        lines.append(f"- {int(s)}: {g['study_title'].iloc[0]}{(' (doi ' + doi + ')') if doi else ''}")
    lines += [
        "",
        f"A further {summ['mismatch_confidence_counts'].get('medium', 0)} medium- and "
        f"{summ['mismatch_confidence_counts'].get('low', 0)} low-confidence mismatches (for example points slightly "
        "offshore or just across a border, or a Country label that disagrees with the study title) are listed in "
        "a CSV that I can share if useful. Issue #134 (coordinate cleaning) seems related.",
    ]
    (OUTD / "srdb_issue_draft.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
