# DECISIONS.md — MSHI v3 decision log

Author: Siyeong Park. Log kept by Claude (co-author role). Every decision, deviation, version and
open question, dated. Earlier history (audit, locked test, pilots): `docs/handoff/prep_log.md`.

Conventions: **D-** decision, **DEV-** deviation from the handoff or the brief, **V-** versions/sources,
**Q-** open question for the author, **F-** finding about the handoff. `[UNVERIFIED]` marks anything
that could not be checked.

---

## 2026-11-02 — Phase 0 (housekeeping)

**D-P0-1 Branch.** The brief asks for branch `v3-rebuild`. This cloud session is bound to the
harness branch `claude/mshi-pipeline-v3-rebuild-cg0r7o`, and all work is pushed there; the PR to
`main` will come from it. If the name `v3-rebuild` matters, the branch can be renamed or pushed under
that name on request. Base: `main` @ `a809a97`.

**D-P0-2 Legacy move.** Everything superseded by v3 was moved (with `git mv`, nothing deleted) into
`legacy/`, mirroring the old paths: `src/`, `scripts/`, `run.sh`, `requirements.txt`,
`configs/mshi_geo.yaml`, `data/outputs/`, `data/processed/`, `data/raw/ACQUISITION_MANIFEST.json`,
`figures/`, `deck/`, `tiles/`, the old README and the atlas-branch notes. `legacy/README.md` says what
each item was and why it was superseded. Not moved: `biosensor_samples/` (untouched, see D-P0-6) and
the committed GEE MODIS exports `data/raw/modis/*.tif` (inputs, not outputs; needed in Phase 3).

**D-P0-3 v1 tables / demo table.** `data/processed/training_features.parquet` at HEAD was the 3,000-row
synthetic demo table (SHA-256 `2ffe0fe5…e016`). The real 615-site v1 Asia table exists in history at
`c6450a7` (2026-05-07, "Replace synthetic training_features.parquet with real Asia + US tables"); the
merge `5c1e5a7` silently reverted it. Both are kept: the real table restored to
`legacy/data/processed/training_features.parquet` (same 615 `site_id`s as the v2 table, identical
values on all shared columns), the synthetic one renamed
`legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet`. Guard: `mshi.io.read_table` (the
only table reader in the pipeline) refuses anything under `legacy/` except the two allow-listed v2
tables (`configs/v3.yaml: legacy_allowlist`) and refuses any file whose SHA-256 is the demo table's,
under any name or location (`forbidden_sha256`). Tested in `tests/test_guards.py`.

**D-P0-4 Handoff provenance.** The bundle `mshi_v3_handoff.zip` (SHA-256 `e3850c29…20f3`) was copied
unchanged to `docs/handoff/` (50 files, verified identical with `diff -r`). Plan
`ANALYSIS_PLAN_LOCKED.md` SHA-256 `9d50e120…3dac` matches its `.sha256` file and prep_log D9.
The locked result `docs/handoff/results/clean_test_europe.json` SHA-256 `b091795f…d1e6` matches
prep_log §13.

**V-P0-5 Environment.** Python 3.13.18 (linux x86_64), virtualenv `.venv` built with `uv`.
Pinned: numpy 2.5.4, pandas 3.1.0, scipy 1.18.1, scikit-learn 1.9.1, statsmodels 0.15.0,
**xgboost 2.1.4**, pyarrow 26.0.0, rasterio 1.5.2 (GDAL 3.12.2), geopandas 1.2.0, pyproj 3.8.0
(PROJ 9.8.1), shapely 2.2.0, pyogrio 0.13.0, pystac-client 0.9.1, requests 2.34.2, rdata 1.1.0,
matplotlib 3.11.2, pyyaml 6.0.3, pytest 9.2.0. `environment.yml` lists these; `requirements-lock.txt`
is the full transitive lock (`uv pip freeze`). numpy/pandas/xgboost match the handoff environment
(prep_log §1: numpy 2.5, pandas 3.1, sklearn 1.9, xgboost 2.1.4). Not tested: creating the env with
conda (conda is not installed here); the pip route was used for every run.

**DEV-P0-6 pygam dropped.** pygam 0.12.0 (latest) requires scipy < 1.17, which conflicts with the
pinned scipy 1.18.1. The Phase-2 GAM will use statsmodels' `GLMGam` with B-splines, which the brief
allows ("pygam or statsmodels splines").

**D-P0-7 Biosensor.** `biosensor_samples/` not touched, not read, not used, and will be excluded from
the paper's data-archive manifest. **Flag for the author:** raw biosensor traces are public in this
repository (`biosensor_samples/`, 6 trial folders, ~19 MB) and, per prep_log §5, also in
`MSHI-WEB/public/data/biosensor_raw/`. Check whether this is compatible with the separate biosensor
manuscript under review.

## 2026-11-02 — Phase 1 (v3 pipeline as a package)

**D-P1-1 Package.** `mshi/` with one entry point `python -m mshi.run --stage all` (also `make all`).
Stages: fetch_srdb, fetch_cosore, fetch_naturalearth, cosore_annual, build_sites, site_diagnostics,
fetch_worldclim, fetch_soilgrids, modis_points, features, clean_test, repro_checks (+ smoke_subset in
`--smoke` runs). Every source version, path, threshold and seed is in `configs/v3.yaml`. A stage whose
source cannot be reached is logged as `blocked` and its dependants are skipped (never mocked).
Output layout: `data/raw/` (downloads, gitignored), `data/interim/` (regenerable; gitignored),
`data/derived/` (small committed tables), `results/` (committed JSON; `run_log.jsonl` holds the
timestamps and run times, so result JSON files are deterministic).

**V-P1-2 Sources fetched and verified (2026-11-02).**
| Source | Pin | Check |
|---|---|---|
| SRDB | `bpbond/srdb` @ `02163a720bc0b84bd535ad0962c85735816448e8`, `srdb-data.csv` | SHA-256 `c4d7714a…2911` = pinned ✔; 14,169 rows |
| COSORE | `bpbond/cosore` v0.8.0 @ `02f32e8e7f9a0f1c26c9dad61c574aef863f1df1` (2021-07-16) | shallow fetch of exactly that commit, HEAD verified ✔; 94 dataset dirs (3 TEST) |
| Natural Earth | v5.1.2 GeoJSON, `nvkelso/natural-earth-vector` @ `f1890d9f…` | SHA-256 recorded; `master` HEAD (`ca96624`, 2022-06-02) has byte-identical files |

**DEV-P1-3 Natural Earth version.** The handoff does not record which Natural Earth release it used
`[UNVERIFIED]`. v5.1.2 is used; since master has not changed since 2022 and every site-build count
(including the 26 coordinate-mismatch examples) reproduces exactly, it is very likely the same data.

**V-P1-4 Network policy blocks three pinned sources (2026-11-02).** This session's egress policy
denies `geodata.ucdavis.edu` (WorldClim 2.1), `maps.isric.org` (SoilGrids WCS) and
`planetarycomputer.microsoft.com` + `modiseuwest.blob.core.windows.net` (MODIS COGs), as well as
`api.crossref.org` and `doi.org` (reference checks), `naciscdn.org` (Natural Earth, GitHub mirror used
instead), `worldclim.org`, `zenodo.org`. Reachable: GitHub, raw.githubusercontent.com, PyPI,
conda.anaconda.org, `esa-worldcover.s3.eu-central-1.amazonaws.com`. Consequence: stages
fetch_worldclim, fetch_soilgrids, modis_points, features and clean_test could not run, so the
locked-test reproduction and the NPP correlation are **NOT RUN**. No mirror or substitute data were
used. The code for these stages is complete and unit-tested on small synthetic rasters only.

**F-P1-5 Reproduction of the site build: exact.** All 17 count targets reproduce exactly (not just
within tolerance): 4,771 SRDB records after repo filters; 4,781 after the coordinate check; 3,694 after
QC; QC removals 450 / 260 / 252 / 243 / 57; QC sites 387 / 257 / 236 / 42 / 26 / 23 (971); repo sites
1,225 (482 / 328 / 284 / 61 / 40 / 30); 605 / 776 sites with ≥ 2 records; COSORE 66 sites. The v3
`results/build_sites.json` equals the handoff `build_summary.json` on every key (test
`test_build_summary_identical_to_handoff`).

**F-P1-6 COSORE "24 files fail with the Python rdata parser" is not correct.** With rdata 1.1.0, **no**
COSORE file fails to parse. The 24 datasets without an annual value are: 6 with no `data/data.RDS` in
the package (data hosted elsewhere, e.g. `d20190526_MINIONS_BNZ` → ORNL DAAC), 17 that parse but have no
port with ≥ 150 observation days spanning ≥ 180 days (surveys, diel or short campaigns), and 1
(`d20200407_WANG`) whose CO₂ flux column is missing in all 72,312 rows. The handoff's "1 no qualifying
port" is actually `d20200331_PEICHL`, dropped because its annual value (26 g C m⁻² yr⁻¹) is below the
50 g floor. Reading the files with R `readRDS` would therefore change nothing; it was not attempted.
The handoff's bookkeeping counted every "no annual value" case as "RDS unreadable".

**F-P1-7 COSORE licence is CC-BY-4.0, not MIT.** The brief states "SRDB and COSORE are MIT". At the
pinned commit COSORE's `DESCRIPTION` says `License: file LICENSE`, and `LICENSE` is Creative Commons
Attribution 4.0 International (SHA-256 `d60376da…5df7`); its README says "Only free use data (CC BY 4)
accepted". SRDB is MIT (Copyright 2018 Ben Bond-Lamberty). Consequence: attribution is required
when redistributing COSORE-derived tables, and COSORE asks users to cite each dataset's primary
publication: `cosore_annual.csv` now carries `primary_publication` (50 of 66 datasets list a DOI) and
`acknowledgment`. Licence notices are in `data/derived/README.md`.

**D-P1-8 Handoff quirks kept for reproduction (not fixed; fixes proposed for author approval).**
Quantified by `site_diagnostics` (`results/site_diagnostics.json`):
1. *Coordinate check in Web Mercator.* "> 100 km from the reported country" is measured in EPSG:3857,
   which inflates distances by 1/cos(latitude) (median ratio 1.35 over the 138 mismatches). With true
   (geodesic) distances 42 records would be flagged instead of 52: the 10 extra are 6 India→Pakistan
   (33.0 N 73.0 E; all alkali-method, so outside the QC set anyway), 1 China→Vietnam and 3
   Italy→Malta (95–98 km true). Using true distances would add 4 records to the QC set, including the
   Malta records in **Europe**, so it could move the locked test set (Europe n). Decision for the author.
2. *Nearest-continent fallback (50 km) in EPSG:3857.* No impact: all 4 off-land records are > 50 km
   from land in true distance too (Japan 167 km; North Sea 83 km; a longitude-sign error near Tasmania;
   one record with longitude 193.9°).
3. *5-km connected components chain.* 17 of 605 multi-record QC sites span > 5 km between their
   farthest records, 2 > 10 km, maximum 15.7 km. Small; kept.
4. *Country names missing from the alias table* (Czechoslovakia, French Guiana, Micronesia, Republic of
   Congo; 12 records) cannot be distance-checked and are never flagged. All 12 lie in or beside the
   intended country; no impact.
5. *MODIS windows read `boundless` with fill 0*, and 0 is a valid NPP value, so window cells beyond the
   edge of a MODIS tile count as NPP = 0 (pulls NPP down for sites within ~3 km of a tile edge; unit
   test `test_read_windows_mean_and_edge_quirk`). Impact on real sites not yet measurable (PC blocked).

**D-P1-9 Locked test re-runs.** `clean_test` refuses to run, and writes nothing, unless (1) the plan's
SHA-256 equals `clean_test.plan_sha256`, (2) it equals the hash in `ANALYSIS_PLAN_LOCKED.sha256`, and
(3) the canonical JSON of the locked definition in `configs/v3.yaml` (candidate sets, learners and
parameters, selection rule, CV and bootstrap settings, seeds) hashes to `clean_test.locked_sha256`
(`822f2ce1…cafa`). Re-runs write `results/clean_test_rerun_{qc,repo}.json` with a `vs_locked` block;
the locked result in `docs/handoff/results/` is primary and is never overwritten. `tests/test_guards.py`
checks refusal on a modified plan, a whitespace change, a mismatched sidecar, and five kinds of edits to
the locked definition, and that the config's locked block matches the plan text.

**D-P1-10 Tolerances.** "±1%"/"±2%" read as relative to the handoff value, "±0.01" as absolute.
Europe n (no tolerance given) is checked at ±2% like the other site counts.

**D-P1-11 Additions that change no reproduced number.** Records table carries extra SRDB columns
for later phases (`srdb_row` = original CSV row index, raw coordinate strings `lat_str`/`lon_str` for
the coordinate-precision analysis, Study_number, Author, Site_ID, Biome, Leaf_habit, Species,
Partition_method, Elevation, Stage) and per-record site ids for both variants.

**D-P1-12 Feature tables not committed (yet).** `features_v3_*.parquet` will contain WorldClim values;
WorldClim's licence terms could not be read (worldclim.org blocked) `[UNVERIFIED]`, so feature tables go
to `data/interim/` (gitignored) until checked. MODIS and ESA CCI terms likewise `[UNVERIFIED]`. No
derived raster is committed.

**V-P1-13 Run times (2026-11-02, 4 vCPU).** fetch_srdb 1.7 s; fetch_cosore 11 s (374 MB shallow
clone); fetch_naturalearth < 1 s; cosore_annual 34–41 s; build_sites 3–4 s; site_diagnostics 2 s;
test suite 53 s. Not measurable here: WorldClim download, SoilGrids WCS (8 × global 0.05° GeoTIFF),
MODIS points (handoff: LST ≈ 45 min for 1,530 points at 32 threads).

## Open questions for the author

**Q-1 Network access.** To finish Phase 1 (locked-test reproduction, NPP check) the environment needs
these hosts allowed: `geodata.ucdavis.edu`, `maps.isric.org`, `planetarycomputer.microsoft.com` and
the Planetary Computer blob storage (`modiseuwest.blob.core.windows.net`; Phase 3 also needs the
storage accounts behind `esa-worldcover`, `esa-cci-lc`, `io-lulc-annual-v02` `[UNVERIFIED host names]`),
plus `api.crossref.org` for reference checks.
**Q-2 Coordinate check.** Keep the Web-Mercator distance (reproduces the locked data) or switch to
true distance (+4 QC records incl. Malta/Europe; would be reported as a deviation from the locked data)?
**Q-3 Branch name.** Keep `claude/mshi-pipeline-v3-rebuild-cg0r7o` or also publish as `v3-rebuild`?
**Q-4 Biosensor traces** public in this repo (D-P0-7).
