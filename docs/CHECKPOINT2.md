# Checkpoint 2 — end of Phase 2 (2026-11-03)

All five Phase-2 analyses (brief §5) are implemented, tested and reviewed once. **Only the noise ceiling could run
on real data**: everything else needs the gridded features, whose hosts this session still cannot reach (§2). The
author's Checkpoint-1 decisions are implemented (`docs/DECISIONS.md` D-C1-1–D-C1-8, D-P2-1–D-P2-17). Everything in
this report is exploratory. **Phase 3 has not been started.**

## 1. Results (exploratory)

### Noise ceiling (brief §5 item 3)

`results/noise_ceiling.json`, figure `figures/phase2/noise_ceiling.png` (and `.pdf`). 3-level REML (site / study
within site / record) of log Rs on the analysis QC records, by geographic continent. A ceiling is the R² that a
perfect predictor of the given kind could reach. From `make all` at the clean commit `880162e`.

| Continent (sites fitted / all) | Sites with ≥ 2 studies | New record, independent study | New record, same study (a predictor of the study) | Same study, best site-constant predictor | Site mean (the Phase-2 target) |
|---|---|---|---|---|---|
| Asia (236 / 386) | 98 | 0.63 [0.51, 0.70] | 0.84 [0.77, 0.89] | 0.81 [0.74, 0.85] | 0.70 [0.59, 0.77] |
| Europe (135 / 233) | 46 | 0.57 [0.40, 0.72] | 0.75 [0.65, 0.82] | 0.73 [0.63, 0.80] | 0.65 [0.47, 0.79] |
| North America (168 / 246) | 56 | 0.81 [0.75, 0.87] | 0.89 [0.85, 0.92] | 0.88 [0.84, 0.91] | 0.87 [0.81, 0.91] |
| South America (33 / 44) | 10 | 0.68 [0.45, 0.84] | 0.68 [0.45, 0.84] | 0.68 [0.45, 0.84] | 0.81 [0.61, 0.92] |
| Africa* (16 / 28) | 2 | 0.09 [0.00, 0.57] | 0.94 [0.86, 0.97] | 0.91 [0.81, 0.95] | 0.09 [0.00, 0.58] |
| Oceania* (14 / 28) | 3 | 0.11 [0.00, 0.83] | 0.89 [0.73, 0.94] | 0.85 [0.72, 0.90] | 0.12 [0.00, 0.86] |
| All six pooled (602 / 965) | 215 | 0.68 [0.62, 0.73] | 0.84 [0.81, 0.87] | 0.82 [0.79, 0.85] | 0.75 [0.69, 0.79] |

95% CIs: site-cluster bootstrap within continents, 200 replicates; in Africa 176 and in Oceania 195 of them could separate site from study variance (the rest are excluded and counted); no refit failed. * Fewer than 30 sites:
supplementary; with 2–3 multi-study sites their site/study split is barely identified. South America's study
variance is at the boundary (0), so its record ceilings coincide.

How to read it:
- The site-mean ceiling is the one that bounds Phase 2's transfer R² (the target is each site's mean log Rs, and
  gridded predictors are constant within a 5-km site).
- "Same study" is the brief's ceiling for a new record from an observed study. A gridded predictor reaches it only at
  single-study sites; the column next to it is what such a predictor can reach (D-P2-17).
- The within-site variance includes real plot-to-plot differences (ecosystem type, F-H19), not only measurement
  error.
- Records from different studies at one site differ more than records of the same study (N3 redone with
  clustering; semivariance difference): Asia 0.056 [0.015, 0.101], Europe 0.100 [−0.002, 0.192], North America 0.040 [0.016, 0.061], pooled 0.062 [0.028, 0.103]; in South America the reverse, −0.135 [−0.260, −0.001].

For scale only: the locked Europe R² is 0.079 [0.013, 0.125] (the locked result file; country-rule Europe, the
handoff's COSORE; not re-run here). Europe's site-mean ceiling is 0.65 [0.47, 0.79], so noise alone does not explain the poor
transfer.

### Not run: these need the gridded features (§2)

| Brief §5 item | Stage | State |
|---|---|---|
| 1 Continent matrix and leave-one-continent-out (OLS-TP, GAM, RF tuned by nested spatial CV, XGB) | `transfer_matrix` | implemented, tested on synthetic data, reviewed |
| 2 Within-continent benchmark: kNNDM (ported from CAST 1.2.0) and 5° blocks | `within_continent` | same |
| 4 AOA sensitivity (threshold × weights) and global DI map at 0.5° | `aoa_sensitivity` | same |
| 5 Why the original US R² was low (E4/E4b re-run) and its figure | `us_r2` | same |
| Q-5 geographic-Europe sensitivity (must reproduce n = 231, R² 0.0598 [−0.001, 0.098]) | `europe_geo_sensitivity` | same; needs the locked-test features |
| Phase 1: locked-test re-run, NPP check | `clean_test`, `repro_checks` | same |

Once the hosts are reachable, `make all` runs all of them (MODIS ≈ 1 h). A later-phase stage runs only if the
reproduction table is current and has no FAIL or STALE row, and if every row it builds on has run (D-P2-14).

## 2. Network (Q-1)

The proxy still refused every host below at 09:49 UTC on 2026-11-03 (connection refused at the proxy; it answered
403 to CONNECT): `geodata.ucdavis.edu` (WorldClim), `maps.isric.org` (SoilGrids),
`planetarycomputer.microsoft.com` (MODIS catalog and tokens), `modiseuwest.blob.core.windows.net` (MODIS data) and
`api.crossref.org` (reference checks). If the environment's network setting was changed, the change has not
reached this session.

Storage hosts for Phase 3 (your Q-1 question), from Microsoft's ingest configuration for the Planetary Computer
(`microsoft/planetary-computer-tasks`, read 2026-11-03), not yet confirmed against the live catalog, which is
blocked here (D-C1-1):
- ESA WorldCover: `ai4edataeuwest.blob.core.windows.net`;
- ESA CCI land cover: `landcoverdata.blob.core.windows.net`;
- the MODIS products, NPP, GPP and NDVI included: `modiseuwest.blob.core.windows.net`;
- Esri 10-m land cover (`io-lulc-annual-v02`): not found there `[UNVERIFIED]`;
- tokens for all of them come from `planetarycomputer.microsoft.com`.

## 3. What changed since Checkpoint 1

- **Your decisions** are logged as D-C1-1–D-C1-8, with your Q-7 timestamps (F-C1-7). The Q-8 wording is used in
  every text written since; three phrases in the dated handoff critique were reworded to it.
- **A second site build for all new work** (`build_sites_analysis`; the locked build is unchanged and still
  reproduces all 17 site-build rows exactly).
  - COSORE is restricted to untreated soil-respiration ports with full-year coverage (DEV-C1-6, D-P2-1): 39 sites
    instead of 66. A port's annual value weighs every month equally.
  - Distances are geodesic (D-P2-2). The coordinate check now flags 42 records instead of 52 (Malta passes).
  - Each site has a geographic continent (D-P2-3, D-P2-12). QC sites: Asia 386, North America 246, Europe 233,
    South America 44, Africa 28, Oceania 28 (965 in all; the locked build has 971).
  - Two edge cases of the continent rule were corrected before any gridded result exists: Russia east of the
    antimeridian is Asia, and South Georgia is South America. No site changed.
- **The reproduction gate** (D-P2-5, D-P2-14):
  - A target outside tolerance stops every later stage (stop and report).
  - A row that could not run holds back only the stages that build on it. So the noise ceiling, which uses only the
    site records, could run while the locked-test rows wait for the network.
- **The reproduction never waits for Phase-2 code** (D-P2-13): the locked chain's MODIS extraction no longer reads
  the analysis build. The 18 analysis-only points get their own small extraction after the gate.
- **The geographic-Europe sensitivity is fixed in code** (D-P2-4) before any of its results exists. Its control: the
  full locked set must reproduce the locked metrics exactly. Its result is compared with your reference.
- **The Phase-2 methods** are D-P2-7–D-P2-11, D-P2-15 and D-P2-16:
  - kNNDM, ported from the authors' R code (the paper and CRAN are blocked here);
  - the learners, metrics and CIs;
  - the noise-ceiling model;
  - the AOA variants;
  - the US R² re-run;
  - the GAM weight cap and the ice sheets left out of the kNNDM domain.

## 4. The code review

One round, as you asked. Four reviewers ran code against four areas, and an adversarial verifier re-ran every
finding (record: `docs/review/2026-11-03/`). There were 17 findings; after verification 1 was high, 3 medium and
13 low. All are fixed (D-P2-13–D-P2-17 and the list after them).
- **Only one changes a computed number.** The noise ceiling's bootstrap refits sometimes missed the REML maximum,
  because statsmodels' optimiser reports convergence at an infinite log-likelihood or short of the maximum. This made
  South America's CIs too narrow: site-mean ceiling now [0.61, 0.92], was [0.64, 0.92]. Now every refit reaches the REML
  maximum: in all replicates of four continents it matches an independent REML to 1e-9. No point estimate changed.
- **Fixed before any result exists.**
  - The GAM's penalty search could run into a range where statsmodels mis-fits (weights capped).
  - North America's kNNDM domain included the Greenland ice sheet (now left out).
  - The reproduction of the locked test could be held up by a failure of exploratory code (MODIS extraction split).
  - The gate behaved differently depending on how stages were invoked (now one rule).
- **Checked and found correct, among others:**
  - the COSORE rule, recomputed from the raw files for all 629 ports;
  - kNNDM, re-derived line by line from CAST's R code;
  - no leakage of test outcomes;
  - an end-to-end run of every Phase-2 stage on stand-ins, byte-identical on re-run.

## 5. Questions for the author

- **Q-9 Network.** The hosts in §2 are still refused in this session. Could you check the environment's network
  setting? If it is already saved, a new session on this branch may be needed. I cannot tell from here whether a
  running session picks the change up.
- **Q-10 Countries on two continents** (D-P2-12). `continent_geo` keeps them whole, except Russia (split at 60°E).
  No QC site is affected; 2 repo-variant sites in European Turkey are labelled Asia. Keep them whole, or split
  Turkey at the Bosporus and Dardanelles?
- **Q-11 The rest of Q-2.** Records whose coordinates are right but whose `Country` label is wrong are still dropped
  by the 100-km rule in the analysis build. Keep dropping them, or keep them?
- **Q-12 COSORE fluxes outside [−2, 50] µmol m⁻² s⁻¹** are clipped, as in the handoff. Dropping them instead would
  lower one site's annual value (LIU) by 24% and move every other site by 6% or less (the review's computation).
  Clip or drop?
- **Q-13 Choices made without you, each fixed before any result.** Say if you want any changed:
  - the noise ceiling uses the nested model only; F-H26's crossed site × study model is not fitted;
  - the RF tuning grid is 3 × 2 (for run time);
  - the AOA thresholds are the brief's two; CAST's own whisker rule is implemented but not configured;
  - kNNDM uses great-circle distances and area-weighted prediction points, without the ice sheets;
  - GAM penalty weights are capped at 1e8;
  - E4's rows on the original 889 sites are not re-run.
- **Q-14 Phase 3.** May I draft the Phase-3 analysis plan now, while the network is blocked, for you to read before
  I commit it? It would fold in the corrections you listed: geographic continents, geodesic distances, the COSORE
  restriction, and no number that code has not computed. It would also say "analysis plan written, committed and
  hashed before the analysis". Nothing in Phase 3 would be computed before you approve it.
