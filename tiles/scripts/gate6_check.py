"""Gate 6: validate documentation."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "tiles"


def main() -> int:
    results = []

    # 1. All three docs exist
    docs = {
        "README.md": TILES / "README.md",
        "PIPELINE_AUDIT.md": TILES / "PIPELINE_AUDIT.md",
        "NIGHT_1_SUMMARY.md": TILES / "NIGHT_1_SUMMARY.md",
    }
    all_exist = all(p.exists() for p in docs.values())
    results.append((
        "all_three_docs_exist",
        all_exist,
        ", ".join(f"{n}={'OK' if p.exists() else 'MISSING'}"
                  for n, p in docs.items()),
    ))

    # 2. NIGHT_1_SUMMARY has clear status in first 200 words
    summary = (TILES / "NIGHT_1_SUMMARY.md").read_text()
    first_200_words = " ".join(summary.split()[:200])
    has_pass = "PASS" in first_200_words
    has_partial = "PARTIAL" in first_200_words
    has_failed = "FAILED" in first_200_words
    status_ok = (has_pass or has_partial or has_failed)
    status = "PASS" if has_pass and not has_partial and not has_failed else \
             ("PARTIAL" if has_partial else "FAILED" if has_failed else "MISSING")
    # The task says status must be PASS/PARTIAL/FAILED. We're claiming PARTIAL.
    results.append((
        "status_in_first_200_words",
        status_ok,
        f"first 200 words mention status: '{status}'",
    ))

    # 3. Concrete hosting recommendation
    has_vercel = "Vercel" in summary
    has_cloudflare = "Cloudflare" in summary or "R2" in summary
    has_mapbox = "Mapbox" in summary
    n_concrete = sum([has_vercel, has_cloudflare, has_mapbox])
    hosting_ok = n_concrete >= 1
    results.append((
        "hosting_recommendation",
        hosting_ok,
        f"concrete options mentioned: Vercel={has_vercel}, "
        f"Cloudflare/R2={has_cloudflare}, Mapbox={has_mapbox}",
    ))

    # 4. Quality flags section
    has_quality_section = bool(re.search(r"##\s*[Qq]uality\s*flags", summary)
                                or re.search(r"##\s*[Qq]uality\s*flags?\s*[—\-:]", summary))
    has_concerns = ("synthetic" in summary.lower()
                    or "limitation" in summary.lower()
                    or "uncertain" in summary.lower())
    quality_ok = has_quality_section and has_concerns
    results.append((
        "quality_flags_honest",
        quality_ok,
        f"has section={has_quality_section}, mentions concerns={has_concerns}",
    ))

    n_pass = emit(results)
    (TILES / "intermediate" / "gate6_results.json").write_text(
        json.dumps([{"name": n, "pass": bool(ok), "detail": str(d)}
                    for n, ok, d in results], indent=2)
    )
    return 0 if n_pass == len(results) else 1


def emit(results):
    print("\nGATE 6 RESULTS")
    print("=" * 78)
    n_pass = 0
    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        if ok:
            n_pass += 1
        print(f"  [{flag}] {name}: {detail}")
    print("=" * 78)
    print(f"Total: {n_pass}/{len(results)} passed")
    print("=" * 78)
    return n_pass


if __name__ == "__main__":
    raise SystemExit(main())
