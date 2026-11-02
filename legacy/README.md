# legacy/ — superseded v1/v2 pipeline, outputs and notes

Everything in this folder was moved here on 2026-11-02 at the start of the v3 rebuild
(see `docs/DECISIONS.md`, entry D-P0-2). Nothing was deleted; paths inside the folder
mirror where each file used to live. **Nothing in `mshi/` reads from `legacy/`**, except
the two original v2 feature tables listed under "Still read by v3", which are read
only for reproduction checks against the original pipeline.

Why the whole pipeline was superseded (from the 2026-11-01 audit, `docs/handoff/prep_log.md`):

- The US test set was used for model and feature selection (at least 8 configurations
  scored on it), so the Asia → US transfer numbers are not a clean test.
- Sites were selected with bounding boxes (the "Asia" box includes European Russia,
  Estonia and Finland; the "US" box includes Canada and Mexico), one arbitrary record was
  kept per 0.05° cell, and no measurement-quality filters were applied.
- WorldClim, SoilGrids and MODIS came from different products and resolutions whose
  provenance could not be fully recovered (WorldClim resolution `[UNVERIFIED]`, SoilGrids
  resampling `[UNVERIFIED]`).
- The methods page describes a hyperparameter sweep and RF/MLP comparisons that exist
  nowhere in this repository or its history.

v3 rebuilds the data from pinned public sources (SRDB, COSORE, Natural Earth, WorldClim
2.1, SoilGrids 2.0, MODIS C6.1) in the `mshi/` package; see the top-level README.

## Contents

| Path (under `legacy/`) | What it was | Why superseded |
|---|---|---|
| `README_v1.md` | Old top-level README ("MSHI-Atlas … 1 km … validated on a US held-out subset") | Describes the v1/v2 pipeline and claims (1 km resolution, held-out US test) that the audit did not support. |
| `notes/CLAUDE_CODE_PROMPT_v1.md` | Instruction set for the original hero-map run (Genius Olympiad) | Belongs to the v1 pipeline. |
| `notes/BLOCKERS_atlas_global.md`, `notes/COMMIT_NOTES_atlas_global.md` | Notes from the 2026-06-02 "atlas global coverage" branch (website atlas) | Website work, built on the superseded F+NPP model. |
| `run.sh` | v1/v2 entry point (`bash run.sh demo|download|…|all`) | Replaced by `python -m mshi.run --stage …` / `make all`. |
| `requirements.txt` | Unpinned requirements (`xgboost>=2.0`) | The original numbers depend on xgboost 2.1.4; replaced by `environment.yml` + `requirements-lock.txt`. |
| `configs/mshi_geo.yaml` | v1/v2 configuration (bounding boxes, XGBoost params) | Replaced by `configs/v3.yaml`. |
| `src/` | v1/v2 pipeline modules: `build_target.py` (SRDB+COSORE → 0.05° dedup table), `features.py`/`extract_features_real.py` (raster sampling), `train.py` (XGBoost + spatial CV + SHAP), `validate.py` (Asia → US test), `predict.py`, `composite.py` (climate-anomaly ratio), `hero_map.py`, `visualize.py`, `download.py`, `demo_synthetic.py` (synthetic smoke test) | Replaced by `mshi/`. Note `train.py` uses the validation fold as the early-stopping set (fold leakage if used). |
| `scripts/task1_*.py` … `task5_*.py` | "Run A" analyses: manipulation-filter relaxation, 6-config sweep, bootstrap CIs, alternative metrics, dual hero maps, dual-region SHAP | All scored on the US set (test-set reuse); `task2_*` read `training_features.parquet`, which was the synthetic demo table at HEAD (see below). |
| `scripts/item1_c*.py` | "Item 1": MODIS sampling, F+NPP and Full+MODIS training, sweep v2, F+NPP hero map, evolution panel, SHAP v2 | Produced the website's headline numbers; superseded by the v3 rebuild and the locked Europe test. |
| `scripts/checkpoint5_koppen.py`, `checkpoint6_panel.py`, `igbp_step*.py` | Köppen and IGBP stratified transfer tests and panels | Scored on the US set; the Köppen classes are a bioclim heuristic, not the Köppen–Geiger map. |
| `scripts/phase_a1.py`, `phase_a234.py`, `diagnose*.py`, `extract_*.py`, `grid_only.py` | Unit checks, spot checks, diagnostics, partial re-extractions | v1/v2 feature tables only. |
| `scripts/presentation_fixes*.py`, `regen_*.py`, `plot_fnpp_scatter_n223.py` | Figure re-renders for the poster and website | Figures of superseded results. |
| `scripts/build_atlas_lookup.py`, `build_atlas_global.py` | Build `atlas_lookup.json` for the website's /atlas page | Website artefacts from the superseded F+NPP / Full+MODIS models. |
| `scripts/cosore_aggregate.py` | Original COSORE → annual Rs aggregation | Logic carried into `mshi/data/cosore.py` with pinned COSORE v0.8.0 input (the original input file was never in the repo). |
| `data/outputs/` | All v1/v2 outputs: metrics JSON, sweep results, SHAP figures, hero maps (PNG/PDF), stratification tables, `paper_results_draft.md`, `atlas_lookup.json`, `genius_pitch_deck.pptx`, run summaries | Results of the superseded pipeline (US-test reuse; see above). |
| `data/processed/training_features.parquet` | **Real** v1 Asia-box training table, 615 sites (605 SRDB + 10 COSORE), restored from commit `c6450a7` (2026-05-07) | At HEAD `a809a97` this path held the synthetic demo table: the merge `5c1e5a7` silently reverted `c6450a7`'s real table. Restored here so the v1 record is complete. Same 615 `site_id`s as `training_features_v2.parquet`, identical values on all shared columns. |
| `data/processed/training_features_SYNTHETIC_DEMO.parquet` | **Synthetic** 3,000-row demo table (`source == "synthetic"`), SHA-256 `2ffe0fe5…e016` | This is what `data/processed/training_features.parquet` contained at HEAD. Kept (not deleted) under an unmistakable name. `mshi.io.read_table` refuses this file by hash and refuses everything under `legacy/` that is not explicitly allow-listed. |
| `data/processed/us_validation_features.parquet` | Real v1 US-box table, 274 sites | v1 table (bounding boxes, US-test reuse). |
| `data/processed/training_features_v2.parquet`, `us_validation_features_v2.parquet` | v1 tables + MODIS NPP/LST from the GEE export (615 / 274 sites) | Superseded, but **still read by v3** for two reproduction checks: the NPP correlation (r = 0.982 target) and the E4 ablation on the original 889 sites. |
| `data/processed/asia_predictions_F_NPP.parquet`, `hero_*_anomaly.parquet`, `asia_grid_demo_anomaly.parquet` | 5-km Asia prediction grids and anomaly composites for the hero maps | Outputs of the superseded models (the demo anomaly file is a 2-byte placeholder). |
| `data/raw/ACQUISITION_MANIFEST.json` | Manifest of the v1 raw downloads (WorldClim 10′ etc.) | The rasters it lists were never committed; v3 fetches pinned sources itself. |
| `figures/validation_scatter_fnpp_n223.png` | F+NPP Asia → US scatter (n = 223) | Superseded result. |
| `deck/build_pitch_deck.js` | Generator for the Genius Olympiad pitch deck | Presentation material for the superseded results. |
| `tiles/` | PMTiles raster tile pyramid of the F+NPP anomaly map for the website, with its phase scripts and audits | Website artefact (MSHI-WEB is out of scope for v3). Note that `tiles/README.md` still describes the first, synthetic run ("a spatial perturbation has been added … hand-tuned regional patterns"); `tiles/NIGHT_1_REAL_DATA_SUMMARY.md` says the shipped file was regenerated from the real F+NPP model. |

## Still read by v3

| File | Read by | Purpose |
|---|---|---|
| `legacy/data/processed/training_features_v2.parquet` | `mshi.analysis.repro_checks`; `mshi.data.modis.modis_point_set` | NPP correlation with the original pipeline at the original sites (the 889 original site coordinates are added to the MODIS point set; not in smoke runs); E4 ablation (Phase 2). |
| `legacy/data/processed/us_validation_features_v2.parquet` | same | same |

The allow-list lives in `configs/v3.yaml` (`legacy_allowlist`), with each file's SHA-256: an allow-listed
path whose bytes change is refused like any other legacy file.

## Not moved

- `biosensor_samples/` — the centimeter-tier biosensor data belong to a separate
  manuscript and are out of scope for v3 (left untouched).
- `data/raw/modis/*.tif` — the committed GEE exports (MODIS NPP/LST 2020–2024 means and
  MCD12Q1 IGBP 2023 land cover, 0.05°, Asia + US + part-of-Oceania footprint). They are
  inputs, not outputs, and cannot be re-fetched without Earth Engine credentials;
  v3 uses the land-cover raster for the plot-vs-pixel comparison (Phase 3).
