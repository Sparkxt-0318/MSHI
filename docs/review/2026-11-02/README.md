# Reviews of 2026-11-02 (Checkpoint 1)

Four reviews were run at the end of Phase 1: the handoff critique, the package review, and two checks of
the fixes (the second review checks the package-review fixes, the third check the fixes made after the
second review). Each finding was produced by one reviewer and then checked by a second, adversarial
reviewer who re-ran it; the verdicts and corrections are included. Summaries and decisions are in
`docs/DECISIONS.md` (F-H-* for the handoff critique, R-P1-14 for the package review, R-P1-20 and R-P1-21
for the two checks of the fixes).

| File | What it is |
|---|---|
| `package_review.md` | Review of the v3 `mshi/` package (fidelity to the handoff scripts, guards and robustness, conformance to the brief): 27 findings, all confirmed and all fixed in the same commit (tests in `tests/test_guards.py`, `tests/test_robustness.py`). |
| `handoff_critique.md` | Critique of the handoff scripts and results (data build, locked test, transfer/noise experiments, the plot-vs-landscape argument): 42 findings, 41 confirmed, 1 uncertain. |
| `critique_scripts/` | The critique's scripts and small text outputs, by lens (`<lens>/` = reviewer, `verify-<lens>/` = verifier). |
| `fix_verification.md` | Second review, after the fixes (`b74e590`): every one of the 27 fixes re-run (all hold), and 20 new findings (all confirmed, all low), each with the verifier's notes and the fix applied (DECISIONS R-P1-20). |
| `fixcheck_scripts/` | The second review's scripts and small logs (`fidelity/`, `guards/`, `spec/` = reviewers; `verify-fidelity2/`, `guards-verify/`, `spec-adv/` = verifiers). Some copy the package or handoff scripts into a sandbox; they ran against offline fakes (local rasters, fake STAC catalogs, local servers). |
| `fix_verification_3.md` | Third check, after the second round of fixes (`a6c00bc`): the 20 fixes re-run (16 hold, 4 partly), the whole pipeline run end to end on stand-ins for the blocked sources, and 22 new findings (18 distinct; 21 confirmed, 1 uncertain; all low), each with the verifier's notes and the fix applied (DECISIONS R-P1-21). |
| `fixcheck3_scripts/` | The third check's scripts and small logs (`chain/`, `modis-rasters/`, `repro-guards-docs/`, `end-to-end/` = reviewers; `verify-<reviewer>/` = verifiers). They ran against offline stand-ins (synthetic rasters, fake STAC catalogs, local servers, copies of the package); copies of the package or repository, large intermediates and file-metadata snapshots were not archived. |

Status of these files: **exploratory review material, not part of the pipeline.** The scripts were run
once in the build container against the pinned inputs (SRDB `c4d7714a…`, COSORE v0.8.0, Natural Earth
v5.1.2) and the handoff bundle; they contain absolute paths of that container's scratch directory
(`…/scratchpad/critique/…` = `critique_scripts/…` here) and will not run elsewhere unedited. Large
intermediate files (parquet, GeoTIFF, CSV) were not archived. Some scripts copy handoff scripts
(`build_sites_v3*.py`, `cosore_aggregate*.py`, `clean_test.py`, ...) to re-run them in a sandbox.

Where WorldClim, SoilGrids or MODIS values were needed (all three sources are blocked in the build
environment), the reviewers used **proxies** (SRDB-reported MAT/MAP, or values borrowed from the
nearest original v1/v2 site). Numbers obtained that way are estimates, are labelled as such in
`docs/DECISIONS.md`, and must be recomputed with the pipeline before any of them is used.
Europe: some critique scripts compute proxy re-scores of the locked Europe test to size the effect of a
problem in the test-set definition. They change nothing (the locked result is final and primary) and
are exploratory.
