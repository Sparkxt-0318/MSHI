# Checkpoint 1 — end of Phase 1 (2026-11-02)

Phase 0 (housekeeping) and Phase 1 (the v3 pipeline as a package) are done as far as this environment
allows. Work is on branch `claude/mshi-pipeline-v3-rebuild-cg0r7o`. Details: `docs/DECISIONS.md`;
reproduction table: `results/reproduction_check.md`; reviews: `docs/review/2026-11-02/`.
**Phase 2 has not been started.**

## 1. Reproduction table

From `make all` at the clean commit `7f7263c` (`results/reproduction_check.md`):

| Quantity | Handoff | v3 | Tolerance | Status |
|---|---|---|---|---|
| COSORE sites with an annual value | 66 | 66 | exact | PASS |
| SRDB records after repo filters | 4,771 | 4,771 | exact | PASS |
| Records after coordinate check / after QC | 4,781 / 3,694 | 4,781 / 3,694 | ±1% | PASS (exact) |
| QC removals: method / quality / coverage / ecosystem / duplicate | 450 / 260 / 252 / 243 / 57 | 450 / 260 / 252 / 243 / 57 | ±2% | PASS (exact) |
| QC sites: Asia / N America / Europe / S America / Africa / Oceania (total) | 387 / 257 / 236 / 42 / 26 / 23 (971) | 387 / 257 / 236 / 42 / 26 / 23 (971) | ±2% | PASS (exact) |
| Repo-filter sites total | 1,225 | 1,225 | ±2% | PASS (exact) |
| Locked test: model; Asia CV R²; Europe n; Europe R² [site-bootstrap CI] | OLS-TP; 0.143; 235; 0.079 [0.013, 0.125] | — | same model; ±0.01; exact; ±0.01 | **NOT RUN** (WorldClim, SoilGrids, MODIS blocked) |
| Locked-test re-runs identical to the locked results (primary; repo-filter sensitivity) | identical | — | 1e-9 | **NOT RUN** (same) |
| NPP r vs committed NPP (889 original sites) | 0.982 | — | ±0.01 | **NOT RUN** (Planetary Computer blocked) |

All 17 site-build targets reproduce **exactly**, not just within tolerance. The v3 build summary equals
the handoff's `build_summary.json` on every key, and the prototype script and the v3 port produce
byte-identical site tables from the same inputs. The locked-test re-runs and the NPP check could not
run. Their code is complete and tested offline, but it has never been run against the real servers.

## 2. What blocked the rest

This environment's network policy refuses `geodata.ucdavis.edu` (WorldClim 2.1),
`maps.isric.org` (SoilGrids WCS), `planetarycomputer.microsoft.com` and its blob storage
(`modiseuwest.blob.core.windows.net`) for MODIS, and `api.crossref.org`/`doi.org` for reference checks.
No mirror or substitute data were used. These hosts are needed to finish Phase 1, and Crossref for the
references in Phase 3/4. Phase 3 also needs the Planetary Computer storage accounts behind ESA WorldCover,
ESA CCI land cover and Esri LULC (host names `[UNVERIFIED]`). To allow them: open the cloud
environment menu in the session's title bar → Edit → Network access, and either pick a broader level or
add the hosts under *Allowed domains* (keep *Allow package managers* ticked). See
https://code.claude.com/docs/en/cloud-environments#network-access. Then `make all` completes the
reproduction. The table rows will show PASS, FAIL or DEVIATION, and a FAIL stops the run.

## 3. Deviations from the handoff and the brief

None of these changes a reproduced number.

- **COSORE licence is CC-BY-4.0, not MIT** (the brief says MIT). Attribution is required: each dataset's
  primary publication is carried in `data/derived/cosore_annual.csv` (F-P1-7).
- **pygam dropped.** It needs scipy < 1.17, but scipy 1.18.1 is pinned. The Phase-2 GAM will use
  statsmodels splines (DEV-P0-6).
- **Natural Earth version.** The handoff does not record it. v5.1.2 is used, and every count, including
  the 26 coordinate-mismatch examples, reproduces exactly (DEV-P1-3).
- **Branch name.** The session branch is used instead of `v3-rebuild` (D-P0-1, Q-3).
- **Locked test, config representation.** Constants that were literals in the prototype (learner list,
  ln(bio12), AOA whisker, CI quantiles, DI terciles) now sit in the hashed config block. Its hash changed
  (`822f2ce1…` → `ef029090…`); the plan and its hash did not. On synthetic data the old and new code give
  bit-identical results except random-forest entries, which differ at the 1e-16 to 1e-15 level (D-P1-9).
- **Random-forest predictions single-threaded.** The handoff summed trees in thread order, so its RF
  values were not reproducible run to run. The effect is 1e-16 to 1e-15 in RF table entries and
  data-dependent; OLS-TP (the locked model) and XGB values are bit-identical (DEV-P1-15).
- **MODIS stage** (DEV-P1-16). A raster read that still fails after retries now fails the stage, and so
  does a catalog that lacks an expected year, month or a month's first 8-day composite (the prototype
  averaged whatever it got). Means are taken in a fixed order. The cache is keyed on the MODIS config,
  the point set, the module source and library versions, and bound to the cached table's bytes. LST
  items with the same date are ordered by id, which can change an LST mean only if the catalog has such
  ties; each tie is listed in `results/modis_points.json`, as is any period outside 2020–2024 that the
  catalog returns (used, as in the prototype).
- **Europe n is checked exactly.** The brief gives no tolerance, and the test set is closed (D-P1-10).
- **NPP r method `[UNVERIFIED]`.** No handoff script computes 0.982, so the v3 check is a reconstruction
  (F-P1-19).

## 4. Run times (4 vCPU)

`make all` with cached raw inputs, from the clean commit `7f7263c`: 49 s (cosore_annual 38 s, build_sites 4 s, site_diagnostics 2 s, each cached fetch ≤ 0.6 s, each blocked stage 0.4 s); exit code 2 (three sources blocked). First fetches: SRDB 1.7 s, COSORE 11 s (374 MB). Tests (`make test`): 171 tests, 167 passed and 4 skipped (the two locked-test re-runs, the locked-test targets and the NPP check, all not run), 69 s. Not measurable here: WorldClim, SoilGrids and MODIS (the handoff reports ≈ 45 min for the LST points).

## 5. What in the handoff is wrong

Two reviews, with every finding re-run by an adversarial verifier: the handoff critique (42 findings,
41 confirmed) and the package review (§6). The full list is in `docs/DECISIONS.md` (F-H1–F-H43, F-P1-6,
F-P1-7, D-P1-8). The ones that matter most:

1. **The locked "Europe" test set contains non-European sites (F-H1, high).** The plan's continent rule
   uses the Natural Earth country polygon, so French Guiana and the Canary Islands count as France and
   Spain. 4 of the 236 QC "Europe" sites are outside Europe: 2 at Paracou, French Guiana, and 2 on
   Tenerife. The v3 pipeline itself reports them (`results/site_diagnostics.json`). The two Paracou
   sites are among the highest-Rs sites in the set. *Reviewers' estimate with proxy climate (not a
   pipeline number):* without them the Europe R² would be about 0.06 rather than 0.079, and the
   site-bootstrap lower bound would drop by about 0.02, to roughly −0.01, so H1 would probably not hold.
   The code follows the plan exactly, so this is a flaw in the plan. The locked result stays primary. I
   propose a declared sensitivity analysis on geographic Europe, decided on geography, not on the score
   (Q-5).
2. **"Europe has never been used to score any model" is false (F-H2).** 30 of the 236 QC Europe sites
   (12.7%) were in the original 25–180° E "Asia" training table: Estonia 13, Finland 8, Russia 7, Latvia
   1, Romania 1. 28 of them hold the identical SRDB record (pipeline numbers: `site_diagnostics`, item 5).
   They were scored as held-out sites in the earlier cross-validation. No number changes; the word
   "untouched" must.
3. **The coordinate check breaks the plan's own rule for Malta (F-H3).** Malta's records lie 95–98 km
   from Italy, but more than 100 km in the Web-Mercator distance the code uses. 28 of the 52 "coordinate
   errors" have correct coordinates and a wrong country label (Q-2).
4. **The lock is internally time-stamped only (F-H4).** The prototype never hashed the plan; it copied
   the hash from the sidecar file (v3 now verifies it). The plan's first git commit is this rebuild's
   (2026-11-02), after the scoring. The paper should say "plan written and hashed before scoring", not
   "pre-registered".
5. **"Deviation from plan: none" is inaccurate (F-H5).** There is an unplanned AOA group rule, the
   baseline MAE is missing, an unplanned DI-tercile output exists, and the tie-break differs from the
   plan text. Malta (item 3) is one more. Whether E1–E5 ran before the scoring is unknown (Q-7).
6. **H1's interval is conditional on one fitted model (F-H6).** Training-sample uncertainty is about
   twice the margin, and the 2° block-bootstrap lower bound is −0.0003. **"No practical gain in g C"**
   depends on the back-transform and on the choice of baseline (F-H7).
7. **COSORE "Rs" includes heterotrophic, NEE and manipulated ports (F-H11).** 3 datasets have no
   untreated Rs port at all. "Annual" values extrapolate growing-season means and clip implausible
   values (F-H12). "24 files rdata cannot read" is wrong: none fails to parse (F-P1-6).
8. **MODIS.** NPP windows are diluted by zeros at tile edges (21 QC sites; F-H13). The "0.05° window" is
   1–9× wider east–west than stated (F-H14).
9. **Phase-2 claims.** "Transfer penalty ≤ 0.09" holds only for leave-one-continent-out; pairwise
   penalties reach 0.18–0.24 (F-H18). The noise ceiling and the N3 intervals ignore clustering
   (F-H19, F-H20). The XGB experiments ran under xgboost 3.4.1, not the pinned 2.1.4 (F-H21).
10. **Phase-3 argument.** The 68.5% vs 30.1% forest contrast depends on counting woody savanna as
    non-forest; counted as forest, the landscape share is 47.7% (F-H31). The 4.3% inflation is mostly
    a smearing artefact (F-H32). "3–13 Pg C/yr" is computed by no script (F-H35). The ~10 m
    coordinate claim has no code behind it (F-H36). These must shape the Phase-3 pre-registration.

## 6. Package review and verification of the fixes

- **First review** (`package_review.md`, R-P1-14): 27 confirmed problems in the first v3 package
  (1 high, 7 medium, 19 low). None changed a reproduced number. The most serious: MODIS values computed
  after failed reads would have been cached silently; the lock could be bypassed by re-hashing the
  config; a stale result could show PASS. All fixed in `b74e590`.
- **Second review** (`fix_verification.md`, R-P1-20): all 27 fixes re-run and hold. It found 20 new
  problems, all confirmed and all low. None changed a reproduced number. The main ones: a stage run on
  upstream outputs from another config looked current (provenance was per stage, not transitive); the
  MODIS cache key missed part of the extraction code and did not bind the cached table's bytes; a short
  STAC catalog was accepted as complete; rasters were not verified when read. All 20 were fixed in
  `a6c00bc`: results record the hash of the files they write for later stages, a stage reads another
  stage's files only if they are recorded outputs of a current result, and stages after the
  reproduction table run only if it has no FAIL or STALE row.
- **Third check** (`fix_verification_3.md`, R-P1-21): the 20 fixes re-run (16 hold, 4 partly), and the
  whole pipeline run end to end on stand-ins for the blocked sources (synthetic rasters, a fake STAC
  catalog, a synthetic target; nothing real scored). The end-to-end run works: every stage ran, a
  second run made no download and wrote byte-identical results, and the 17 site-build rows equal the
  committed values. 18 new problems (22 reports), all low; none changed a reproduced number. Several
  came from the second-round fixes themselves. The main ones: results were not bound to the upstream
  results they read, so a re-fetched unpinned source (WorldClim, SoilGrids, MODIS) could leave stale
  locked-test rows looking current; committed results would have read as stale on a fresh clone
  (gitignored outputs absent); a failed upstream stage could turn FAIL rows into NOT RUN and open the
  gate; pinning the WorldClim hash deleted the downloaded data; a Finder `.DS_Store` in the COSORE
  checkout stopped `make all`; a Windows (CRLF) checkout made every result stale. All 18 are fixed in
  `7f7263c`, with tests (33 of the 36 new or changed test cases fail on the previous commit; the rest
are older cases or an anchor). Results now also record the upstream results
  they read and are current only if those are unchanged and current; the gate also requires no NOT RUN
  row. Tests: 171 tests, 167 passed, 4 skipped (the checks that need the blocked sources).
- **Stopping here.** The three rounds found 27, 20 and 18 problems, of falling severity (1 high, 7
  medium and 19 low; then 20 low; then 18 low), none of which changed a reproduced number. The main
  remaining risk is the code that cannot run here (rasters, MODIS, the locked-test re-run on real
  features), which the end-to-end run exercised only on stand-ins; it will be checked when the sources
  are reachable (Q-1).

## 7. Decisions needed

- **Q-1** Allow the hosts in §2.
- **Q-2** Coordinate check: keep it as locked, or use true distance and keep label-only errors?
- **Q-3** Branch name.
- **Q-4** Biosensor traces (below).
- **Q-5** Sensitivity analysis on geographic Europe, plus a geographic continent column for the
  exploratory work.
- **Q-6** COSORE target for v3's own analyses: untreated Rs ports only, full-year coverage?
- **Q-7** Did E1–E5 run before the Europe scoring?
- **Q-8** Wording: drop unqualified "untouched" and "pre-registered".

## 8. Flag

Raw centimetre-tier biosensor traces are public in this repository (`biosensor_samples/`, 6 trials,
~19 MB) and, according to prep_log §5, in `MSHI-WEB/public/data/biosensor_raw/`. They were not touched
and will be left out of the paper's data-archive manifest. Please check whether their being public
matters for the biosensor manuscript under review.
