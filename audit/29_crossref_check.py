"""29_crossref_check.py - verify every cited DOI against Crossref (api.crossref.org/works/<doi>).

Input: audit/outputs/references.csv with columns key, doi, expected_title (fragment), cited_for.
For each DOI the script fetches the Crossref record and stores title, container, year, first author,
type and a title-match score (token overlap with the expected fragment). Nothing is cited in the
write-up unless status == "ok" here.

Usage: python -I audit/29_crossref_check.py
Output: audit/outputs/references_crossref.csv
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

UA = {"User-Agent": "mshi-audit-crossref-check/1.0 (research reproducibility script)"}


def toks(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def main() -> int:
    refs = pd.read_csv(C.OUT / "references.csv")
    out = []
    for r in refs.itertuples(index=False):
        doi = str(r.doi).strip()
        rec = {"key": r.key, "doi": doi, "expected_title": r.expected_title, "cited_for": r.cited_for}
        try:
            resp = requests.get(f"https://api.crossref.org/works/{quote(doi, safe='/')}", headers=UA, timeout=60)
            rec["http"] = resp.status_code
            if resp.status_code == 200:
                m = resp.json()["message"]
                title = " ".join(m.get("title", []) + m.get("subtitle", []))
                rec["crossref_title"] = title
                rec["container"] = " ".join(m.get("container-title", []))
                parts = (m.get("issued", {}).get("date-parts") or [[None]])[0]
                rec["year"] = parts[0] if parts else None
                au = m.get("author", [])
                rec["first_author"] = au[0].get("family", au[0].get("name", "")) if au else ""
                rec["type"] = m.get("type")
                e, t = toks(str(r.expected_title)), toks(title)
                rec["title_match"] = round(len(e & t) / max(len(e), 1), 2)
                rec["status"] = "ok" if rec["title_match"] >= 0.6 else "TITLE_MISMATCH"
            else:
                rec["status"] = "NOT_FOUND"
        except Exception as ex:  # noqa: BLE001
            rec["status"] = f"ERROR {type(ex).__name__}"
        out.append(rec)
        time.sleep(0.2)
    df = pd.DataFrame(out)
    df.to_csv(C.OUT / "references_crossref.csv", index=False)
    print(df[["key", "doi", "status", "title_match", "first_author", "year", "container"]].to_string())
    print(df["status"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
