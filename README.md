# MSHI v3 — soil respiration: site data, transfer evaluation and upscaling bias

> **Status (2026-11-03): rebuild in progress — Phase 2 (exploratory) implemented; the results that need
> the gridded sources (WorldClim, SoilGrids, MODIS) wait for network access.** This README is interim; it is
> rewritten for the paper in Phase 4. The previous (v1/v2) pipeline, its outputs and its claims are in
> `legacy/` (see `legacy/README.md` for what each item was and why it was superseded).

v3 rebuilds the kilometre-tier soil respiration (Rs) data from pinned public sources: SRDB v5 and
COSORE v0.8.0 records, Natural Earth countries, WorldClim 2.1, SoilGrids 2.0 and MODIS C6.1. The
Asia → Europe test, whose plan was written and hashed before scoring
(`docs/handoff/ANALYSIS_PLAN_LOCKED.md`), was scored once on 2026-11-01, and its result
(`docs/handoff/results/clean_test_europe.json`) is final.

## Run

```bash
make env                                       # python3.13 venv in .venv from requirements-lock.txt
make all                                       # = python -m mshi.run --stage all
make test                                      # regression, guard, unit, robustness and 50-site smoke tests
```

With conda instead: `conda env create -f environment.yml`, activate it, then the same `make` targets
(the Makefile uses `.venv/bin/python` if it exists, otherwise `python`). `python -m mshi.run --list`
shows the stages. Exit codes: 0 all stages ok; 1 a stage failed or a reproduction target is outside
its tolerance; 2 no failure, but a source was blocked or unreachable, an input was stale (re-run the
upstream stages, e.g. `make all`), or a stage was skipped because of one of these. Stages of later
phases (all exploratory) run only if the reproduction table is current, has no FAIL or STALE row in any
group (a target outside tolerance stops them all: stop and report), and has no NOT RUN row among the rows
they build on (see "Two site builds" below; smoke runs do not apply this gate).

Every source version, path, analysis threshold, reproduction tolerance and seed is in `configs/v3.yaml`;
the code keeps only numerical slack, network retry/timeout defaults and how many examples a result lists.
Downloads go to `data/raw/` (gitignored), regenerable intermediates to `data/interim/` (gitignored), small
derived tables to `data/derived/`, results (JSON) and the run log to `results/`.
`results/reproduction_check.md` compares the outputs with the handoff numbers. Each result JSON carries
`_provenance` (hashes of the config and of the `mshi` code of the run), `_outputs` (SHA-256 of the files
the stage wrote for later stages: tables, rasters, the reproduction table) and `_inputs` (SHA-256 of the
upstream results it read). A result is current only if both hashes match, its output files are
unchanged, and every upstream result it read is unchanged and itself current. Outputs under `data/raw/`
and `data/interim/` are not committed, so on a fresh clone they may be absent without making a result
stale; a stage that needs one refuses to run until it is regenerated. Stages read other stages' files
only if they are recorded outputs of a current result; downloads of pinned sources (SRDB, COSORE,
Natural Earth) are checked against the pinned hashes or commit instead. The reproduction table reports
results that are not current as STALE, and the regression tests fail on them. `.gitattributes` turns
off line-ending conversion for the hashed files, so a checkout on Windows has the same bytes.
`results/run_log.jsonl` is the append-only log of every stage run (times, statuses, commit) on the
machines that produced the committed results; its `blocked` entries describe that machine's network
policy, not a property of the pipeline.

## Two site builds

- **Locked build** (`build_sites`: `data/derived/records_v3.parquet`, `sites_v3_{qc,repo}.parquet`): the
  handoff's rules, kept only to reproduce the locked test (distances in Web Mercator, continents by country,
  the handoff's COSORE rule).
- **Analysis build** (`build_sites_analysis`: `records_analysis.parquet`, `sites_analysis_{qc,repo}.parquet`),
  used for all new work (the author's decisions of 2026-11-03): geodesic distances (`mshi/geo.py`), a
  geographic continent `continent_geo` (Natural Earth map subunits: overseas territories by location), and
  COSORE restricted to untreated soil-respiration ports with full-year coverage
  (`cosore_annual_analysis.csv`). See `docs/DECISIONS.md` D-P2-1 to D-P2-3.

Stages after `repro_checks` (later phases; all exploratory) need a current reproduction table without FAIL
or STALE rows; a stage that uses the gridded features also needs every row to have run, the noise ceiling only
the site-build rows, so it can run while sources for the other rows are unreachable (D-P2-5, D-P2-14). The
decision depends only on the stored table, not on whether `repro_checks` ran in the same invocation. The
locked chain does not read the analysis build: MODIS values for the analysis sites that the locked sites do
not cover come from a separate stage after the gate, `modis_points_analysis` (D-P2-13).

## Where things are

| Path | Contents |
|---|---|
| `mshi/` | the pipeline package (`mshi/run.py` is the entry point) |
| `configs/v3.yaml` | all versions, paths, thresholds, seeds; the hash-locked definition of the clean test |
| `tests/` | reproduction-target regression tests, guards (demo table, locked plan), unit and robustness tests, smoke test |
| `docs/DECISIONS.md` | dated log of decisions, deviations, versions and open questions |
| `docs/CHECKPOINT1.md` | Checkpoint 1 report: reproduction table, deviations, run times, what in the handoff is wrong, decisions needed |
| `docs/CHECKPOINT2.md` | Checkpoint 2 report: Phase-2 results so far, what waits for the network, the review, questions |
| `docs/review/2026-11-02/` | the package review and the handoff critique (findings, verifier notes, review scripts; exploratory) |
| `docs/review/2026-11-03/` | the Phase-2 code review (findings, verdicts, the reviewers' scripts and logs) |
| `docs/handoff/` | the 2026-11-02 handoff bundle (audit log, locked plan, prototype scripts, pilot results) |
| `data/derived/` | COSORE annual values, record and site tables of both builds (with licence and attribution notes) |
| `results/` | stage outputs, `reproduction_check.md`, `run_log.jsonl` |
| `figures/phase2/` | Phase-2 figures (PNG 300 dpi and PDF, byte-reproducible) |
| `legacy/` | superseded v1/v2 code, tables, figures and website artefacts |
| `biosensor_samples/` | centimetre-tier biosensor data for a separate manuscript (not used by v3) |
