# MSHI v3 — soil respiration: site data, transfer evaluation and upscaling bias

> **Status (2026-11-02): rebuild in progress — end of Phase 1.** This README is interim; it is
> rewritten for the paper in Phase 4. The previous (v1/v2) pipeline, its outputs and its claims are in
> `legacy/` (see `legacy/README.md` for what each item was and why it was superseded).

v3 rebuilds the kilometre-tier soil respiration (Rs) data from pinned public sources: SRDB v5 and
COSORE v0.8.0 records, Natural Earth countries, WorldClim 2.1, SoilGrids 2.0 and MODIS C6.1. The
pre-registered Asia → Europe test (`docs/handoff/ANALYSIS_PLAN_LOCKED.md`) was scored once on
2026-11-01, and its result (`docs/handoff/results/clean_test_europe.json`) is final.

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
phases run only after a complete, passing reproduction table: current, and no FAIL, STALE or NOT RUN
row (smoke runs do not apply this gate).

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

## Where things are

| Path | Contents |
|---|---|
| `mshi/` | the pipeline package (`mshi/run.py` is the entry point) |
| `configs/v3.yaml` | all versions, paths, thresholds, seeds; the hash-locked definition of the clean test |
| `tests/` | reproduction-target regression tests, guards (demo table, locked plan), unit and robustness tests, smoke test |
| `docs/DECISIONS.md` | dated log of decisions, deviations, versions and open questions |
| `docs/CHECKPOINT1.md` | Checkpoint 1 report: reproduction table, deviations, run times, what in the handoff is wrong, decisions needed |
| `docs/review/2026-11-02/` | the package review and the handoff critique (findings, verifier notes, review scripts; exploratory) |
| `docs/handoff/` | the 2026-11-02 handoff bundle (audit log, locked plan, prototype scripts, pilot results) |
| `data/derived/` | COSORE annual values, record and site tables (with licence and attribution notes) |
| `results/` | stage outputs, `reproduction_check.md`, `run_log.jsonl` |
| `legacy/` | superseded v1/v2 code, tables, figures and website artefacts |
| `biosensor_samples/` | centimetre-tier biosensor data for a separate manuscript (not used by v3) |
