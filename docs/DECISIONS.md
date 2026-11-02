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
`legacy/data/processed/training_features_SYNTHETIC_DEMO.parquet`. Guard: `mshi.io.read_table` refuses
anything under `legacy/` except the two allow-listed v2 tables (`configs/v3.yaml: legacy_allowlist`) and
refuses any file whose SHA-256 is the demo table's, under any name or location (`forbidden_sha256`).
Tested in `tests/test_guards.py`. *Amended 2026-11-02 after the package review (R-P1-14):* the original
claim that `read_table` was "the only table reader" was false (three direct `pd.read_parquet` calls on
the MODIS cache); it is now true and enforced by a test that scans `mshi/` for direct readers. The guard
also hashes every file inside a directory dataset, refuses any table whose `source` column contains
`synthetic` (re-encoded copies of the demo table have another hash), compares the `legacy/` prefix
case-insensitively, and accepts an allow-listed file only if its SHA-256 equals the one pinned in the
config.

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
`--smoke` runs). Every source version, path, analysis threshold, reproduction tolerance and seed is in
`configs/v3.yaml` (*amended 2026-11-02, R-P1-20 and R-P1-21:* the re-run deviation tolerance
(`clean_test.deviation_atol`), the minimum number of sites for the NPP r (`repro_checks.npp_min_sites`) and
the off-land search radius and site-diameter bins of `site_diagnostics` were code literals and are now in
the config; the code keeps only numerical slack, 1e-12 in tolerance comparisons, network retry/timeout
defaults and how many examples a result lists). A stage whose source the egress proxy refuses is logged as
`blocked`, one whose source cannot be reached as `unavailable` (*corrected 2026-11-02, R-P1-21:* this said
`blocked` for both; D-P1-18); their dependants are skipped (never mocked).
Output layout: `data/raw/` (downloads, gitignored), `data/interim/` (regenerable; gitignored),
`data/derived/` (small committed tables), `results/` (committed JSON; `run_log.jsonl` holds the
timestamps and run times, so result JSON files carry none). *Corrected 2026-11-02 (R-P1-14):* this entry
said "result JSON files are deterministic"; that was not true of the locked-test re-run (random-forest
predictions summed in thread-completion order, ~1e-16) or of MODIS window means (averaged in completion
order). Both are fixed (DEV-P1-15, DEV-P1-16): two runs of the locked test on the same synthetic input
now give byte-identical JSON (SHA-256 `60d102d2…` twice).

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
used. *Corrected 2026-11-02 (R-P1-14):* this entry said the blocked stages were "unit-tested"; several
paths had no test. Now tested offline (tests/test_units.py, tests/test_robustness.py, tests/test_smoke.py):
MODIS window reading, scaling, tiles, token cache, `plan_jobs` (datetime None, first composite per
month, Terra only, composite rule), order-independent aggregation, the second pass and persistent read
failures, the cache key and refusal of stale MODIS values; `attach_features`/`features` on synthetic
rasters; WorldClim zip extraction and reuse; the `clean_test` stage end to end on synthetic data with
light settings; download failure classes against a local server. Never run against the real servers:
the WorldClim download, the SoilGrids WCS request and the Planetary Computer STAC/COG reads.

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

**D-P1-9 Locked test re-runs** (*rewritten 2026-11-02 after the package review, R-P1-14*). The first
version anchored the definition only by a hash stored in the same config (a re-hashed edit, or another
`--config`, passed), left several locked constants in code outside the hash, and its docs claimed more
than it covered. Now `clean_test` refuses to run, and writes nothing, unless
(1) the plan file's SHA-256 = `PLAN_SHA256` anchored in `mshi/analysis/clean_test.py` = the config's
`plan_sha256` = `ANALYSIS_PLAN_LOCKED.sha256` (`9d50e120…3dac`, unchanged);
(2) the canonical JSON of `clean_test.locked` = `LOCKED_SHA256` anchored in the code = the config's
`locked_sha256`;
(3) the two locked result files have the SHA-256s anchored in the code (`b091795f…d1e6`, `48aa5beb…f9db`).
What (2) covers: continents, target, the five predictor sets, `ml_learners` (XGB, RF) + OLS-TP, the
OLS-TP form (`ols_tp`, `ols_tp_log`), all XGB/RF parameters, model seed, CV block size, folds and seeds,
tie margin, bootstrap n/seed, 2° block bootstrap, CI quantiles, seed spread, AOA permutation repeats and
seeds, AOA whisker quantiles and multiplier, AOA minimum group, DI groups, and the RF prediction thread
count. Not covered by a hash, because they are code: the selection loop and tie rule, scoring, metrics
and AOA computation (`LockedTest`, `spatial.block_folds`, `spatial.bootstrap_ci`); these are pinned by
`test_locked_code_unchanged` (SHA-256 of their syntax tree, docstrings excluded, Python 3.13).
*Re-lock of the config representation:* the constants that were literals in code (learner list, OLS-TP
log transform, AOA quantiles 0.25/0.75 and multiplier 1.5, CI quantiles 0.025/0.975, DI terciles) and the
RF prediction thread count (DEV-P1-15) moved into the locked block, so its hash changed from
`822f2ce1…cafa` to `ef029090d17d2a428cff48a710753cee75b63cf2f00748a73f1114798a4dae7f`. The plan file and
its hash are unchanged, no value changed, and no Europe data were used. Evidence: the previous and the
new `LockedTest` run on two synthetic feature tables (real 971-site geometry, synthetic covariates and
target; one selects OLS-TP, the other XGB/ALL, which exercises the seed spread and the permutation-importance
AOA) give bit-identical selection tables, selected models, primary metrics, bootstrap CIs and AOA
results; only random-forest entries differ, at the 1e-16 to 1e-15 level (*corrected 2026-11-02, R-P1-20
and R-P1-21:* this said "the 19 entries, by ≤ 5e-16", then "at the 1e-16 level"; the size is
data-dependent, see DEV-P1-15).
Re-runs write `results/clean_test_rerun_{qc,repo}.json` with `lock`, `_provenance` and a `vs_locked`
block (`identical` = same model and every primary metric within `clean_test.deviation_atol` = 1e-9, a value
pinned by a test since R-P1-21); the
locked result in `docs/handoff/results/` stays primary and is never overwritten. `LockedTest` itself
verifies the lock (only tests on synthetic data may opt out). The stage also refuses feature tables that
are not the recorded outputs of a current `results/features.json` (other code or config, or bytes changed
since; D-P1-17). *Amended 2026-11-02 (R-P1-20):* the lock check also requires `clean_test.variants` to
re-run every locked result (`qc` and the plan-specified `repo` sensitivity), and the reproduction table
reports both re-runs. These edits to the stage wrapper changed the syntax-tree pin of `clean_test.py`
(`66368bfa…` → `31e2f191…`; *R-P1-21:* → `0feeaa0f…`, because the wrapper now records `features.json` as
the re-runs' input); the `LockedTest` class (selection, scoring, metrics, AOA) is unchanged, and a second
pin fixes it alone (`9487b2b4…`, identical at `b74e590`, `9e17a36`, `a6c00bc` and now). Tests: refusal for a modified plan (also with
config and sidecar re-hashed), a whitespace change, a mismatched sidecar, 22 kinds of edit to the locked
block each with and without a re-hashed config (the refusal message never prints a replacement hash), an
alternative `--config` file, a modified locked result; every value the plan states is compared with the
plan text, and the others (bootstrap seed, AOA seeds and repeats, minimum group, DI groups, seed range)
with the prototype `docs/handoff/scripts/clean_test.py`.

**D-P1-10 Tolerances.** "±1%"/"±2%" read as relative to the handoff value, "±0.01" as absolute.
*Amended 2026-11-02 (R-P1-14):* Europe n has no tolerance in the brief. It was first checked at ±2%;
it is now **exact**, because the Europe test set is closed and any change in it is a deviation to report
(ground rule 4). The table also has a row "re-run identical to the locked result" (DEVIATION if the
selected model or any primary metric differs by more than 1e-9). *Amended 2026-11-02 (R-P1-20):* a
second such row covers the repo-filter sensitivity re-run, and `tests/test_guards.py` holds a literal copy
of the brief's target table (checked against `PROMPT_mshi_v3.md`), so loosening a target in the config
fails the tests instead of only changing the table. *Amended 2026-11-02 (R-P1-21):* the 1e-9 that separates
PASS from DEVIATION in the re-run rows moved into the config in R-P1-20 without such an anchor (a config
edit could turn a deviation into PASS); `tests/test_guards.py` now pins it too.

**D-P1-11 Additions that change no reproduced number.** Records table carries extra SRDB columns
for later phases (`srdb_row` = original CSV row index, raw coordinate strings `lat_str`/`lon_str` for
the coordinate-precision analysis, Study_number, Author, Site_ID, Biome, Leaf_habit, Species,
Partition_method, Elevation, Stage) and per-record site ids for both variants.

**D-P1-12 Feature tables not committed (yet).** `features_v3_*.parquet` will contain WorldClim values;
WorldClim's licence terms could not be read (worldclim.org blocked) `[UNVERIFIED]`, so feature tables go
to `data/interim/` (gitignored) until checked. MODIS and ESA CCI terms likewise `[UNVERIFIED]`. No
derived raster is committed.

**V-P1-13 Run times (2026-11-02, 4 vCPU).** First fetches: fetch_srdb 1.7 s; fetch_cosore 11 s (374 MB
shallow clone); fetch_naturalearth < 1 s. Full run `make all` from the clean commit `b74e590` (raw
inputs cached): 43 s in total: cosore_annual 33.6 s, build_sites 2.9 s, site_diagnostics 1.9 s, the
cached fetches ≤ 0.4 s each (hash and worktree checks only), each blocked stage 0.3 s; exit code 2
(three sources blocked). The committed `results/` and `data/derived/` come from that run (the derived
tables were byte-identical to the previous ones). Test suite: 110 tests, 107 passed, 3 skipped (the
locked-test re-run and the NPP check, not run), 60 s. Not measurable here: WorldClim download, SoilGrids
WCS (8 × global 0.05° GeoTIFF), MODIS points (handoff: LST ≈ 45 min for 1,530 points at 32 threads).
*Updated 2026-11-02 (R-P1-20):* `make all` from the clean commit `a6c00bc`: 48 s (cosore_annual 37.7 s,
build_sites 3.9 s, site_diagnostics 1.8 s, cached fetches ≤ 0.4 s, blocked stages 0.3–0.4 s), exit code 2;
`data/derived/` byte-identical to before. `make test`: 140 tests, 136 passed, 4 skipped (the two
locked-test re-runs, the locked-test targets and the NPP check), 68 s. *Updated 2026-11-02 (R-P1-21):*
`make all` from the clean commit `7f7263c`: 49 s (cosore_annual 38.0 s, build_sites 3.6 s,
site_diagnostics 2.1 s, cached fetches ≤ 0.6 s, blocked stages 0.4 s), exit code 2; `data/derived/` and
`results/reproduction_check.md` byte-identical to before (the result JSONs gain `_inputs`, new hashes and,
in `site_diagnostics.json`, the recorded search radius). `make test`: 171 tests, 167 passed, 4 skipped
(the same four), 69 s.

**R-P1-14 Package review (2026-11-02).** The Phase-1 package was reviewed by three independent
reviewers (fidelity to the handoff scripts, guards and robustness, conformance to the brief), and every
finding was then checked by an adversarial verifier, who re-ran it. Result: 27 findings, all
confirmed (1 high, 7 medium, 19 low; *corrected 2026-11-02, R-P1-20:* this said 8 medium and 18 low);
no reproduced number was wrong. Confirmed **correct**: the COSORE and
site-build ports (prototype and port produce byte-identical site tables on the same inputs), the features
and MODIS window logic (identical on synthetic rasters, including the edge quirk), the locked-test port
(bit-identical except random-forest noise), the config values against the prototype literals, the
1,530-point MODIS set, the legacy move (199 renames, nothing deleted), the handoff copy and hashes.
All 27 are fixed in this commit; the main ones:
- *High:* the MODIS stage cached values computed after failed raster reads, ignored MODIS config changes
  on re-runs and erased the failure record (DEV-P1-16).
- *Medium:* the lock was anchored only in the config it guards, and locked constants sat in code
  (D-P1-9); the reproduction table reported PASS from a stale file when the producing stage had just
  failed (D-P1-17); HTTP 404/5xx and server-side 403 were reported as "blocked by network policy"
  (D-P1-18); committed results named the pre-v3 base commit as their provenance (D-P1-17).
- *Low:* a FAIL did not stop the run (D-P1-18); the NPP check's method is reconstructed, not the
  handoff's (F-P1-19); RF and MODIS outputs not bit-reproducible (DEV-P1-15/16); checksum verified after the file was
  moved into place, and pinned raw files not re-verified at read time (both fixed: verified before the
  move, and SRDB/Natural Earth hashes and the COSORE checkout, commit plus clean worktree, are checked by
  the stages that read them); SRDB `LICENSE` re-downloaded on every run (now hash-pinned); `git status`
  could rewrite `.git/index` (now `--no-optional-locks`); command-line stage order not enforced (now
  always pipeline order); `lst.composite` was a dead key (now validated); Europe n tolerance (D-P1-10);
  direct table reads and guard gaps (D-P0-3); untested paths (V-P1-4); the lock file pinned a Linux-only
  wheel without a marker (now carries xgboost's own marker) and `make` assumed `.venv` (now falls back to
  `python`); wrong cross-references in config, code and `legacy/README.md`.

**DEV-P1-15 Random-forest predictions single-threaded.** The handoff fits and predicts with `n_jobs=2`;
scikit-learn then sums the per-tree predictions in thread-completion order, so identical fits give
predictions differing by ~1e-16 between runs. v3 fits with `n_jobs=2` (identical forests) and predicts
with one thread (`rf.predict_n_jobs: 1`, part of the locked block), which fixes the summation order.
Effect (*corrected 2026-11-02, R-P1-20 and R-P1-21*; this said "≤ 5e-16, no other value changes", then
"at the 1e-16 level"): RF entries of the selection table and of `all_candidates_on_test` change at the
1e-16 to 1e-15 level. The size depends on the data: on synthetic tables at the locked settings the second
review measured up to 6.7e-16 absolute, the third up to 1.3e-15 (relative differences are larger where an
R² is near 0). If RF were the selected model, its primary metrics, seed
spread and AOA results would change by similar amounts (up to 5.7e-14 absolute was measured). OLS-TP and
XGB values are bit-identical, so the locked result's model (OLS-TP, CV R² 0.143 vs 0.132 for the best
RF) and every reported number are unaffected. The previous code was not reproducible with itself on RF
entries; the new code is.

**DEV-P1-16 MODIS stage** (*rewritten 2026-11-02, R-P1-20*). Differences from the prototype
`modis_points_lst.py`. When every raster read succeeds and the catalog is complete, (1)-(5), (7) and (8)
change no value; (6) can change an LST mean, and only if two Terra items share the earliest date of a month:
(1) a read still failing after its 4 attempts is retried once more in a second pass with a fresh token;
if any read still fails the stage fails and writes no values (the prototype printed the failure and
averaged the remaining rasters, silently changing those sites' means). The former `max_failed_reads`
setting was removed: any value above 0 made the stage report ok with partial means that `features` then
refused;
(2) the STAC search is checked before any raster is read: every tile needs one NPP item per year of
`datetime` and, in every month, an LST composite dated in the first `lst.composite_days` (8) days of the
month, and no search may return `max_items_per_tile` items (possible truncation). A gap fails the stage,
with every gap listed in `results/modis_points.json`, unless it is listed in
`sources.modis.accepted_catalog_gaps` (empty; entries only after review, with a logged decision). The
prototype averaged whatever the catalog returned, and the v3 cache would have kept such a partial mean
after the catalog recovered. *Amended 2026-11-02 (R-P1-21):* the check was month-granular, so a month whose
first 8-day composite was missing (a later one present) passed, and its mean used the later composite.
MOD11A2 composites start every 8 days (day of year 1, 9, …, 361), so the first composite of every month
starts on day 1–8; this follows the product's 8-day calendar and could not be checked against the live
catalog (blocked). The failure record listed only 100 gaps and counted the planned reads as made; it now
lists every gap and records 0 reads;
(3) per-site means are taken over rasters in sorted (kind, date, href) order, so they do not depend on
thread completion order;
(4) the cache in `data/interim/` carries a key: SHA-256 of `sources.modis`, of the point set, of the whole
`mshi/data/modis.py` source (the first version hashed eight functions, leaving out `extract_points`), and
the numpy, rasterio, GDAL, pyproj and PROJ versions. The sidecar also records the SHA-256 of the cached
table. The cache is reused, and `load_modis_points` (used by `features` and the NPP check) accepts the
table, only if the key and the table's bytes match and the cached run had no failed reads; a cache hit
rewrites the original run's record;
(5) the blob-storage host of the first COG is probed before extraction, so a policy block of that host
is reported as `blocked` instead of yielding all-NaN values. *Amended 2026-11-02 (R-P1-21):* a stale cache
is no longer deleted before a re-extraction; it stays until a new extraction replaces it, so after a
blocked re-extraction `features` and the NPP check report why the old table is refused (status `stale`;
the error is now a `StaleInputError`) instead of a missing file;
(6) LST items are ordered by (date, item id) before taking the first composite of each month; the
prototype ordered by date only, keeping the API's order for identical dates. If the catalog holds two
Terra items on the earliest date of a month, the smaller id is used, and every such tie is listed in
`results/modis_points.json` (`lst_same_date_ties`), so a difference from the handoff can be traced. Whether
the real catalog has such ties is unknown here (blocked). LST enters only the C8+MODIS and ALL
candidates; the locked results select OLS-TP, which uses no LST;
(7) `lst.composite` is read and validated (only `first_of_month`, the handoff rule, is implemented);
(8) (*added 2026-11-02, R-P1-21*) the STAC search returns items whose time span overlaps `datetime`, so a
composite dated outside the range (e.g. one starting in late December 2019 and ending in January 2020, if
the catalog dates it so; not checkable here) can be returned. It is used, as in the prototype (the LST
mean then covers one more month), and every such tile period is listed in `results/modis_points.json`
(`periods_outside_datetime`).

**D-P1-17 Provenance and stale results.** Every stage result JSON now carries `_provenance`: SHA-256 of
the config and of the `mshi` package source. The reproduction table marks a row STALE if its result
came from another config or code, and NOT RUN, with the reason, if the producing stage did not complete
in the current invocation, even when an older file exists. The regression tests fail on a stale result.
*Amended 2026-11-02 (R-P1-20):* provenance was checked per result only, so a stage run on upstream
outputs from another config was stamped current (e.g. `make features` after a config change, without
re-running `build_sites`). Now (a) each result also records `_outputs`, the SHA-256 of the files the
stage wrote for later stages (*corrected 2026-11-02, R-P1-21:* this said "every file the stage wrote"; the
fetch stages of pinned sources record none, because their readers check the pinned hashes or commit, and
cache sidecars are checked by their own stage), and a result is current only if its config and code hashes
match and every recorded output still has its recorded bytes; (b) every stage that reads another stage's files first calls
`require_outputs` (the upstream result is current, records a complete run, and lists those files as its
outputs): `build_sites` for the COSORE table, `site_diagnostics`, `modis_points` and `features` for the
site tables, `features` for the MODIS table and every WorldClim/SoilGrids raster, `clean_test` for the
feature tables; otherwise the stage stops with status `stale`; (c) results carry the config and code
hashes taken when the run started, not when the result was written, so a result never claims code that
was edited while the stage ran; (d) the raster fetches keep a `*.source.json` sidecar with the request
that produced each file and re-fetch when the configured request (e.g. SoilGrids depth or statistic,
WorldClim URL or pinned hash) or the file changes; the SoilGrids file name now includes depth and
statistic. *Amended 2026-11-02 (R-P1-21):* (e) results also record `_inputs`, the SHA-256 of each upstream
result the stage read, and a result is current only if each of those is unchanged and itself current
(checked recursively). Before, a result stayed current when an upstream stage was re-run under the same
config and code but wrote other bytes (an unpinned source fetched again: WorldClim, SoilGrids, a MODIS
re-extraction), so `make features` followed by `make repro` reported locked-test rows from re-runs on
feature tables that no longer existed, and the reproduction gate opened on them; (f) outputs under
`provenance.local_only_roots` (`data/raw`, `data/interim`: gitignored) may be absent without making a
result stale, and `require_outputs` refuses to hand an absent file to a stage. Before, a fresh clone of
results committed from a networked run would have shown the NPP rows STALE and failed `make test`; a test
checks that these roots are exactly the gitignored ones; (g) `Config.root_key` matches paths as written
before resolving symlinks, so a symlinked sub-directory of a root (e.g. `data/raw/worldclim` on another
disk) works again; (h) the raster fetches never delete verified data before a replacement download has
succeeded; the WorldClim pin is verified, not part of the request (pinning the hash a download recorded
needs no request), and the SoilGrids request hash covers the WCS parameters as built by the code, not only
the configured fields; (i) `.gitattributes` turns off line-ending conversion for every hashed path, and
JSON, CSV, Markdown and the run log are written with `\n` on every platform: on a CRLF checkout (Git for
Windows' default `core.autocrlf`, `[UNVERIFIED]` here) every result read as stale and the lock refused.
Each `run_log.jsonl` record carries the git commit (`+dirty` if code, config, tests, environment files
or the handoff bundle have uncommitted or untracked changes), the config and code hashes, and the
requested stages. `results/environment.json` is written only by full (`--stage all`) runs. The
committed `run_log.jsonl` is the log of the machines that produced the committed results, including
this container's network-policy blocks. The first Phase-1 commit's `environment.json` named the pre-v3
base commit (`a809a97+dirty`), because the runs preceded the commit; the committed results are now
regenerated from a clean, committed tree (V-P1-13).

**D-P1-18 Failure classes and exit codes.** Run-log statuses: `ok`; `blocked` (the egress proxy refused
the connection: a network-policy block); `unavailable` (DNS or connection failures, or timeouts, after
retries); `skipped` (an upstream stage of this invocation did not complete); `error` (anything else,
including HTTP 4xx other than 407/408/429 at once, HTTP 408/429/5xx or truncated transfers after
retries, a non-TIFF SoilGrids response, a checksum mismatch, a reproduction FAIL). Exit codes: 0 all ok;
1 any error; 2 no error but something blocked, unavailable or skipped. `repro_checks` writes the table
and then fails if any row is FAIL. *Amended 2026-11-02 (R-P1-20):* (a) new status `stale` (an input
result is not current, D-P1-17, or a reproduction row is STALE), counted in exit code 2; a table whose
rows are all STALE used to exit 0; (b) "later stages will not run on non-reproducing inputs" was not
enforced. Now `run()` skips every stage ordered after `repro_checks` unless `repro_checks` finished `ok`
in the same invocation or, when it is not part of the invocation, the stored table is current and has
no FAIL or STALE row (*amended 2026-11-02, R-P1-21:* and no NOT RUN row, in both cases: a producer that
failed in an invocation turned the current build's FAIL rows into NOT RUN, which opened the gate. Smoke
runs do not apply the gate: their outputs are not results and they never run `repro_checks`, so the gate
would have blocked every later-phase stage in `make smoke`); (c) a policy block is recognised by the tunnel status only (`Tunnel connection
failed: 403/407` from requests, `CONNECT tunnel failed, response 403/407` from git, checked against this
container's proxy). Before, any "403"/"407" in the message counted, so a dead proxy on a port such as
1403 was reported as `blocked` (*amended 2026-11-02, R-P1-21:* `git fetch` failures are classified like
downloads: HTTP 408/429/5xx are retried and then `error`, a proxy that cannot reach the host, CONNECT 5xx,
is retried and then `unavailable`; a 5xx used to fail at once); (d) the COSORE checkout check also refuses
gitignored files (the pinned commit ignores `doc` and `Meta`, so a dataset directory with such a name was
read but invisible to `git status`). *Amended 2026-11-02 (R-P1-21):* the check now covers only the paths
that are read (the datasets directory and the licence) and ignores operating-system metadata files
(`.DS_Store`, `._*`, `Thumbs.db`, `desktop.ini`): refusing every ignored file made opening the checkout in
Finder or RStudio stop `make all`. The checkout converts no line endings (`core.autocrlf false`).

**F-P1-19 The NPP reproduction check is a reconstruction `[UNVERIFIED method]`.** No handoff script
computes "NPP r = 0.982 vs committed" (prep_log D8): `validate_features.py` compares the committed GEE
rasters with the committed tables. v3 uses Pearson r on raw NPP at the 889 original sites with a value in
both tables, joined on `site_key`, which follows the handoff's other "r with committed values"
computation (`validate_features.py`), but whether the handoff used this subset, Pearson or Spearman, raw or
log NPP, is not recorded. The row says so. prep_log D8's second number ("recovers 189 sites lost to masked
pixels") has no tolerance in the brief and is reported as an INFO row.

**R-P1-20 Second review: the fixes verified (2026-11-02).** After `b74e590`, three reviewers (fidelity,
guards, conformance to the brief) re-ran each of the 27 fixes in sandboxes and looked for new problems in
the fixed code; an adversarial verifier re-ran every new finding. Result: **all 27 fixes hold**; **20 new
findings, all confirmed, all low** after verification (the transitive-provenance finding was rated medium
by its finder). None changes a reproduced number: the site build and its tables are unchanged (byte-
identical), and the stages concerned (rasters, MODIS, locked-test re-run) cannot run here. All 20 are fixed
in this commit, with tests (140 tests: guards, robustness, smoke, regression):
- MODIS cache: the key left out `extract_points`, and nothing bound the cached table's bytes, so a
  replaced table, or one written by older code, was accepted as current → DEV-P1-16 (4);
- MODIS catalog shortfall (a missing year or month) was accepted as complete, and cached → DEV-P1-16 (2);
- same-date LST ties changed values without a trace, while the docs said no value changes → DEV-P1-16 (6);
- `max_failed_reads > 0` made the stage report ok with output that `features` refused → removed;
- provenance was not transitive (a stage on upstream outputs from another config looked current); results
  were stamped with the code on disk at write time; rasters were not verified when read, and SoilGrids or
  WorldClim config edits were ignored once files existed → D-P1-17 (a)-(d);
- an all-STALE reproduction table exited 0; "later stages will not run after a FAIL" was not enforced;
  any "403"/"407" in a proxy error counted as a policy block; gitignored files escaped the COSORE
  worktree check → D-P1-18 (a)-(d);
- the repo-filter re-run had no row in the table (a deviation there went unreported), and dropping it
  from `clean_test.variants` was accepted; NPP rows said NOT RUN where STALE or FAIL was right; a re-run
  without `vs_locked` showed NOT RUN with no note → D-P1-9, D-P1-10 and `repro_checks`;
- reproduction targets were anchored only in the config they gate → literal test (D-P1-10); the
  deviation tolerance was a code literal → config (D-P1-1);
- directory datasets: members were only hash-checked (a symlinked legacy table inside a directory was
  read) and a column projection skipped the `source` check → `read_table` refuses directories and checks
  `source` under any projection (none of this was reachable from a pipeline call);
- documentation: the RF effect was overstated as "≤ 5e-16, no other value changes" (DEV-P1-15, D-P1-9);
  R-P1-14 misstated the severity counts.
Also new: `site_diagnostics` item 5, which makes F-H2 a pipeline number. Config changes (the config hash
changes; no reproduced number changes; the locked block and its hash do not change): removed
`sources.modis.max_failed_reads`; added `sources.modis.accepted_catalog_gaps: []`,
`clean_test.deviation_atol: 1.0e-9`, `site_diagnostics.original_asia_table` and `original_asia_box`;
SoilGrids `file_pattern` is now `{var}_{depth}_{statistic}_global_0p05.tif`. Record:
`docs/review/2026-11-02/fix_verification.md` (with the reviewers' scripts in `fixcheck_scripts/`).
*Corrected 2026-11-02 (R-P1-21):* two statements above were too broad. "Checks `source` under any
projection" did not hold for projections combined with options that change the header line, or for a
`source` stored as an index; and the transitive-provenance fix covered a change of config or code, not
upstream content that changed under the same config. Both are fixed in R-P1-21.

**R-P1-21 Third check: the second round of fixes verified (2026-11-02).** After `a6c00bc`, four reviewers
re-ran the fixes of R-P1-20 by area (provenance chain and gate; MODIS and rasters; reproduction table,
guards and docs) and ran `python -m mshi.run --stage all` end to end on stand-ins for the blocked sources
(a synthetic WorldClim zip and SoilGrids GeoTIFFs, a fake STAC catalog and raster reads, a light locked
test with the real lock verified and a synthetic target; nothing real was scored); an adversarial
verifier re-ran every finding. Result: the end-to-end run works (every stage ran; a second run made no
download, re-used the MODIS cache and wrote byte-identical results; a SoilGrids statistic change re-fetched
exactly the 8 rasters; the 17 site-build rows equal the committed values). 16 of the 20 fixes hold, 4
partly. **22 new findings, 18 distinct** (four found by two reviewers): 17 confirmed and 1 uncertain, all
low after verification (one rated medium by its finder). None changes a reproduced number. Several came
from the R-P1-20 fixes themselves (marked †). All are fixed in this commit, with tests; the new test
cases fail on the previous commit (33 of 36 new or changed cases; the 3 others are old cases of a changed
test):
- results were not bound to the upstream results they read, so a re-fetched unpinned source left
  downstream numbers, and the reproduction gate, "current" → D-P1-17 (e);
- † gitignored outputs would have made committed results STALE on a fresh clone → D-P1-17 (f);
- † `root_key` broke a symlinked sub-directory of a root → D-P1-17 (g);
- † pinning the recorded WorldClim hash, or changing the layer count, deleted the verified layers and zip
  before a re-download; a SoilGrids request changed in code reused old rasters → D-P1-17 (h);
- a CRLF checkout made every result stale and the lock refuse; CSV and JSON used the platform line ending
  → D-P1-17 (i);
- † a producer that failed in an invocation turned FAIL rows into NOT RUN and opened the gate; † smoke runs
  could never run a later-phase stage → D-P1-18 (b);
- a refused MODIS table was `error` in `features` but STALE in the table → DEV-P1-16 (5);
- `git fetch` did not retry HTTP 5xx → D-P1-18 (c); † the COSORE worktree check refused harmless OS and
  editor files (.DS_Store, .Rproj.user) → D-P1-18 (d);
- MODIS: a missing first composite of a month passed the catalog check (R-P1-20's fix was partial); the
  failure record counted planned reads as made and cut the gap list at 100; periods outside `datetime`
  were used without a record (the uncertain finding: whether the real catalog returns such items could
  not be checked) → DEV-P1-16 (2), (8);
- `read_table`: a `source` index, or a CSV projection with options that change the header line, escaped
  the content check (R-P1-20's fix was partial) → `mshi/io.py` rule (4), whose docstring now states the
  remaining limit (a renamed column is caught only by the hash rule);
- † `deviation_atol` moved into the config without an anchor → pinned by a test (D-P1-10);
- code literals still decided results (NPP minimum overlap, off-land search radius, site-diameter bins) →
  config (D-P1-1);
- documentation: "every file the stage wrote", "every stage refuses inputs that are not the outputs of a
  current upstream result", "the code keeps only numerical slack and network defaults", the allow-list
  descriptions, D-P1-1's "logged as `blocked`", and the RF effect "at the 1e-16 level" (the third check
  measured 1.3e-15 in an RF table entry) → corrected in README, config comments, `legacy/README.md`,
  D-P1-1, D-P1-9, D-P1-17, DEV-P1-15 and `docs/CHECKPOINT1.md`.
Config changes (the config hash changes; the locked block and its hash do not): added
`provenance.local_only_roots: [raw, interim]`, `sources.modis.lst.composite_days: 8`,
`site_diagnostics.offland_search_deg: 5.0` and `diameter_bins_km: [5, 10, 20]`,
`repro_checks.npp_min_sites: 3`; comments corrected. New `.gitattributes`. The syntax-tree pin of
`clean_test.py` changed (D-P1-9); the `LockedTest` pin did not. Record:
`docs/review/2026-11-02/fix_verification_3.md` (scripts in `fixcheck3_scripts/`). Results regenerated from
the clean commit `7f7263c` (V-P1-13): the same 17 PASS and 10 NOT RUN; 171 tests, 167 passed, 4 skipped
(the locked-test re-runs and the NPP check, which need the blocked sources). Line endings, checked after
the commit: a fresh clone of `d550318` made with `core.autocrlf=true` has no CR byte in the hashed files
(code, plan, reproduction table, COSORE table), all 7 committed results are current, the lock verifies,
and the test suite gives 165 passed and 6 skipped (the 4 above, and 2 that need `data/raw`, which a clone
lacks); a fresh clone of `de236d0` made the same way has CRLF in those files, 0 of 7 results current, and
the lock refuses. Reviews stop here for
Checkpoint 1: the three rounds found 27, 20 and 18 problems, of falling severity (1 high, 7 medium and 19
low; then 20 low; then 18 low), none of which changed a reproduced number; the code that cannot run here
(rasters, MODIS, the locked-test re-run on real features) remains the main risk until the sources are
reachable (Q-1).

## 2026-11-02 — Checkpoint 1: what in the handoff is wrong (F-H)

From the handoff critique (`docs/review/2026-11-02/handoff_critique.md`; 42 findings by 4 reviewers,
each re-checked by an adversarial verifier: 41 confirmed, 1 uncertain). Numbers marked *(review
estimate)* come from the reviewers' scripts in `docs/review/2026-11-02/critique_scripts/`, some with proxy
climate (WorldClim is blocked here); they are not pipeline outputs and must be recomputed before use.
Numbers marked *(pipeline)* come from v3 code. Nothing here changes the locked result, which stays
primary.

### Bearing on the locked Asia → Europe test

**F-H1 (high) The "Europe" test set contains sites outside Europe.** The plan's continent rule (Natural
Earth CONTINENT of the country polygon containing the site) labels overseas parts of France and Spain
"Europe". In the QC table 4 of 236 Europe sites lie outside Europe: 2 at Paracou, French Guiana (5.0° N,
53.0° W) and 2 on Tenerife; the repo-filter table has 5 of 284 (plus a 20-record Gran Canaria site)
*(pipeline: `results/site_diagnostics.json`, `continent_outside_box_*`)*. The code implements the plan
exactly, so this is a flaw in the plan's definition, not a code bug. The two Paracou sites are among the
highest-Rs sites of the set (ranks 2 and 22 of 236). *(Review estimate, two proxy Asia models:)* without
the two French Guiana sites the Europe R² would be about 0.060–0.063 instead of 0.079, and the
site-bootstrap lower bound would drop by about 0.02, so H1 would probably not hold in that
sensitivity analysis. Recommendation: a declared sensitivity analysis "Europe = geographic Europe",
decided on geographic grounds (French Guiana is not in Europe), not because of the Europe score;
reported as a deviation, with the locked result kept primary. For exploratory analyses, a geographic
continent column with an explicit override table (French Guiana → South America, Canary Islands →
Africa, Hawaii flagged). North America also includes 5 Hawaiian QC sites. Decision for the author (Q-5).

**F-H2 (medium) "Europe has never been used to score any model" is not true.** 30 of the 236 QC Europe
sites (12.7%; the locked test scored 235 of them) were in the original 25–180° E "Asia" training table:
Estonia 13, Finland 8, Russia (west of 60° E) 7, Latvia 1, Romania 1. 28 of them contain the identical
SRDB record (same CSV row); the other 2 have a record within 5 km of an original training site. These are
exactly the Europe sites inside the old Asia box. Repo-filter variant: 38 of 284. *Pipeline numbers
since R-P1-20* (`site_diagnostics` item 5, `results/site_diagnostics.json`; the first version of this
entry was the critique's estimate, "about 30"). The original k-fold CV
(`task2_sweep.py`, `item1_c2_train_fnpp.py`, `item1_c3_train_full_modis.py`, the audit's `reproduce.py`)
had no region filter, so these rows were scored as held-out sites, and those fold scores fed the audit's
"Asia-only selection would have picked Full+MODIS" argument. prep_log §3 itself lists the 65 European
sites in the old Asia box. No Europe-specific score was ever computed, and the locked model trains only
on v3 Asia, so no number changes; the words "untouched"/"never used" must change. *(review estimate)*

**F-H3 (medium) Malta is dropped against the plan's own rule.** The plan says "drop records > 100 km from
the reported country"; Malta's records lie 95–98 km (true distance) from Italy but > 100 km in the Web
Mercator distance the code uses (D-P1-8 item 1), so the locked Europe set is one site off its own plan.
Also, 28 of the 52 "coordinate errors" have correct coordinates and a wrong Country label (the point is
where the record's own Site_name/Region says); 24 are real coordinate errors; the alias `Congo` maps
Yangambi (DR Congo) to the Republic of the Congo. A geodesic rule that keeps label-only records would
add 3 Europe, 1 Asia, 1 North America and 1 Oceania QC sites *(review estimate)*. Decision Q-2.

**F-H4 (medium) The lock is internally time-stamped only.** The prototype `clean_test.py` copied the plan
hash from the sidecar file and never hashed the plan (v3 now verifies it, D-P1-9). The plan's first git
commit is this rebuild's Phase-0 commit `b98b2ce` (2026-11-02), about 27 h after the scoring
(~08:25 Z 2026-11-01); `a809a97` has no plan file. So the lock cannot be shown to precede the scoring
from outside the bundle (prep_log already listed this as open). The locked output has no feature hash,
package versions or per-site predictions, and no features table is in the bundle. Wording: "plan
written and hashed before scoring (internal timestamp)", not "pre-registered".

**F-H5 (low) "Deviation from plan: none" (prep_log §13) is inaccurate.** (1) The "> 10 sites on each
side" rule for the AOA contrast is not in the plan, and the planned inside-minus-outside comparison was
never produced (H2 was not testable: 233/235 inside). (2) The plan asks for MAE with the intercept
baseline; the baseline MAE is not computed, and the model MAE is computed but not reported. (3)
`sq_err_by_DI_tercile` is unplanned and unlabelled. (4) The tie-break code chains (F-H8), unlike the plan
text (no effect here). (5) Malta (F-H3). Unknown: whether E1 (Europe ICC) or E5 (trained on 967 sites
including Europe) ran before the scoring; if so, that is a deviation from "only after this test is
scored" (Q-7).

**F-H6 (medium) H1's interval is conditional on one fitted model.** Both CIs resample Europe sites
around a single fit; training-sample uncertainty is not included. *(Review estimate:)* it is about twice
the 0.013 margin of the lower bound. The 2° block-bootstrap lower bound is −0.0003. H1 holds exactly as
pre-specified, but "Europe R² 0.079 [0.013, 0.125]" must say which interval it is.

**F-H7 (medium) "No practical gain in g C units" depends on the back-transform.** Predictions are
back-transformed with a plain exp() (no smearing), and the constant baseline is the Asia geometric mean
(723 g C m⁻² yr⁻¹), which happens to be close to Europe's arithmetic mean (743). The claim is true as
computed, but convention-dependent.

**F-H8 (low)** The tie-break chains (each step compares with the current pick, so the final pick can be
more than 0.01 below the top), and CV folds are re-drawn for each candidate's complete rows. Latent; no
effect on the result (OLS-TP is top). v3 keeps the rule verbatim because it is locked.
**F-H9 (low)** Two "Asia spatial-CV R²" values exist for the same model and rows: 0.143 (mean of 15 fold
R², selection) and 0.163 (pooled out-of-fold, E6). "± 0.076" is a fold SD, not an SE.
**F-H10 (low)** The secondary all-candidate Europe table supports no ranking (marginal CIs, single seed).

### Data build (reproduced exactly as in the handoff; fixes need the author's approval)

**F-H11 (medium) COSORE "Rs" mixes in heterotrophic, NEE and manipulated ports.** `PORTS.txt` is never
read. Of 308 qualifying ports in the 66 datasets, 64 (15 datasets) are not untreated Rs: 46 Rh, 14 NEE,
3 manipulated. Three datasets have no untreated Rs port at all: HIRANO_PDB (Rh only; Asia),
UEYAMA_HOKUROKU (NEE; Asia), UEYAMA_FAIRBANKS (clear-chamber NEE; Alaska). Restricting to Rs/None ports
raises log Rs by up to 0.22 at six sites. Effect on the headline small *(review estimate)*. Fix:
keep ports with `CSR_MSMT_VAR == "Rs"` and `CSR_TREATMENT == "None"` (not the opacity filter, which
would drop 11 legitimate datasets).

**F-H12 (medium) COSORE "annual" values extrapolate growing seasons.** Annual Rs = mean of all clipped
observations × one year, pooled over years. 23 of 66 sites have no qualifying port covering all 12
months. In 26 full-year temperate/boreal datasets the April–November mean is 1.32× the 12-month mean.
Clipping keeps implausible values at the bounds (PANG: 1,308 g C kept vs 544 if they were dropped).
The docstring says multi-year sites are averaged; the code pools them. *(review estimate)*

**F-H13 (medium) MODIS NPP tile-edge zeros** (D-P1-8 item 5, confirmed down to rasterio's VRT path).
21 QC sites affected (Asia 11, North America 6, Europe 4), 8 of them with exactly half the window outside
the tile. The "NPP r = 0.982" target partly includes this bug. Not the OLS-TP result. *(review estimate)*

**F-H14 (low)** The MODIS "0.05° window" is the bounding box of the projected corners, so it is 1–9×
wider east–west than 0.05°, more so in East Asia and western North America than in Europe.
**F-H15 (low)** COSORE "24 unreadable" = 0 parse failures (F-P1-6).
**F-H16 (low)** The "QC removals" are overlapping per-flag counts, not a sequence.
**F-H17 (low)** A site's plot type breaks ties alphabetically (Agriculture beats Forest, Forest beats
Grassland), ±1.5 points on the N2 forest share.

### Bearing on Phase 2 (transfer and noise; the claims will be re-derived, not reproduced)

**F-H18 (high)** "Transfer penalty ≤ 0.09 R²" holds for leave-one-continent-out only; pairwise penalties
reach 0.18 (OLS-TP, NA → Asia, R² −0.015) and 0.24 (XGB), with no uncertainty anywhere.
**F-H19 (medium)** The E1 noise ceiling (0.84) treats records as independent replicates and pools
continents; with study clustering the per-continent ceilings are 0.66–0.85.
**F-H20 (medium)** N3's pair bootstrap treats pairs as independent; the CIs are 3.6–8.3× too narrow (the
contrast itself survives a site-cluster bootstrap).
**F-H21 (medium)** The E2/E3/E4/E6 XGB numbers were not produced with the pinned xgboost 2.1.4 (the README
says 3.4.1) and change when re-run (E4 CI lower bound 0.021 → 0.000).
**F-H22 (medium)** E4's "site-mean vs single-record target: no change" holds for continents only.
**F-H23 (medium)** E3's "no concept shift / equal slopes except NPP" is not supported (single seed, no CI;
NPP p = 0.022 does not survive Holm over 5 tests).
**F-H24 (medium)** Transfer "skill" is relative to the training continent's mean, so it rewards fixing the
between-continent offset and is not comparable with within-continent skill.
**F-H25 (medium)** E5's 87.3 Pg C/yr is a median-based sum (no retransformation), over a grid including
ice sheets and barren land.
**F-H26–F-H30 (low)** N3 nesting (70 studies span several sites; a crossed model moves ~4 points of
variance share); two Asia CV R² definitions (F-H9); E2's soil-vs-NPP contrasts unpaired, single seed;
E4/E4b do not reproduce the original configuration and do not name their filter set; the prep_log §12
clay correlations have no script.

### Bearing on Phase 3 (plot vs landscape; to be handled in the pre-registration)

**F-H31 (high)** "68.5% of plots are forest vs 30.1% of the landscape" counts IGBP 8 (woody savanna,
30–60% tree cover) as non-forest. With IGBP 8 as forest the landscape share at plots is 47.7%: the gap
drops from 38 to 21 points, and claims (2) and (3) move too.
**F-H32 (high)** The 4.3% binary "inflation" is largely an artefact of one pooled Duan smearing factor
under class-heteroscedastic errors; with class-specific smearing or a log-link GLM it is about 0–2%, CIs
spanning 0.
**F-H33 (uncertain)** The 15% upper end rests on a 5-plot Savanna class; pooling under the brief's own
< 20-plot rule changes it, but the result depends on the merge target.
**F-H34 (high)** Claim (2) (plot vs pixel coefficient) is never tested as a difference; the paired CI
includes 0, the attenuation reading has no power, and the "forest" effect is not forest-specific
(grassland plots equal forest plots given climate).
**F-H35 (high)** "3–13 Pg C/yr globally" is computed by no script; the likely arithmetic mixes
retransformation scales, models and domains.
**F-H36 (medium)** "Holds for coordinates precise to ~10 m" is backed by no code; ≥ 4 decimals is not
10 m (many are minute-level DMS conversions, ±0.9 km); about 36–39 forest plots; and precision cannot
address a 5.5-km cell mismatch.
**F-H37–F-H43 (medium/low)** "4–15%" should read 4.1–13.0% (inflation is A/C − 1, reduction 1 − C/A); the
"Asia + US footprint" is about 20% Africa and Europe by area, with no plots there; N2 Q2 plot-type effects
are silently empty (substring-filter bug), and pixel effects use Agriculture as reference; N2 Q4 R²
compares different samples and drops a failed fold; the plot and "true landscape" labels come from the
same product (identification); the N2 crosstab JSON is transposed relative to its name; samples differ
across N2 files; bootstrap details (few draws, unpaired resamples, map and crosswalk uncertainty
excluded).

## Open questions for the author

**Q-1 Network access.** To finish Phase 1 (locked-test reproduction, NPP check) the environment needs
these hosts allowed: `geodata.ucdavis.edu`, `maps.isric.org`, `planetarycomputer.microsoft.com` and
the Planetary Computer blob storage (`modiseuwest.blob.core.windows.net`; Phase 3 also needs the
storage accounts behind `esa-worldcover`, `esa-cci-lc`, `io-lulc-annual-v02` `[UNVERIFIED host names]`),
plus `api.crossref.org` for reference checks.
**Q-2 Coordinate check.** Keep the Web-Mercator distance (reproduces the locked data) or switch to
true distance, and keep records whose coordinates are right but whose Country label is wrong (F-H3)?
Either change would be reported as a deviation from the locked data.
**Q-3 Branch name.** Keep `claude/mshi-pipeline-v3-rebuild-cg0r7o` or also publish as `v3-rebuild`?
**Q-4 Biosensor traces** public in this repo (D-P0-7).
**Q-5 Europe test set (F-H1).** Approve a declared sensitivity analysis on geographic Europe (without
French Guiana; Canary Islands in or out?), and a geographic continent column for the exploratory
analyses? The locked result stays primary either way.
**Q-6 COSORE target (F-H11, F-H12).** For v3's own analyses (not the reproduction), restrict COSORE to
untreated Rs ports, and require full-year coverage (or month-balanced means, dropping out-of-range values
instead of clipping)? Each would change the COSORE site count from 66 and would be logged as a deviation.
**Q-7 Order of analyses (F-H5).** Did E1–E5 (prep_log §12) run before the Europe scoring on 2026-11-01?
**Q-8 Wording (F-H2, F-H4, F-H6, F-H7).** The paper should not say "untouched" or "pre-registered"
without qualification; agreed?
