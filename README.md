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
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt   # or: conda env create -f environment.yml
.venv/bin/python -m mshi.run --list            # stages and dependencies
.venv/bin/python -m mshi.run --stage all       # or: make all
make test                                      # regression, guard, unit and 50-site smoke tests
```

Every source version, path, threshold and seed is in `configs/v3.yaml`. Downloads go to `data/raw/`
(gitignored), regenerable intermediates to `data/interim/` (gitignored), small derived tables to
`data/derived/`, results (JSON) and the run log to `results/`. `results/reproduction_check.md` compares
the outputs with the handoff numbers.

## Where things are

| Path | Contents |
|---|---|
| `mshi/` | the pipeline package (`mshi/run.py` is the entry point) |
| `configs/v3.yaml` | all versions, paths, thresholds, seeds; the hash-locked definition of the clean test |
| `tests/` | reproduction-target regression tests, guards (demo table, locked plan), unit tests, smoke test |
| `docs/DECISIONS.md` | dated log of decisions, deviations, versions and open questions |
| `docs/handoff/` | the 2026-11-02 handoff bundle (audit log, locked plan, prototype scripts, pilot results) |
| `data/derived/` | COSORE annual values, record and site tables (with licence and attribution notes) |
| `results/` | stage outputs, `reproduction_check.md`, `run_log.jsonl` |
| `legacy/` | superseded v1/v2 code, tables, figures and website artefacts |
| `biosensor_samples/` | centimetre-tier biosensor data for a separate manuscript (not used by v3) |
