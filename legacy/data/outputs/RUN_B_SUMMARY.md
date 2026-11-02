# Run B — partial overnight summary

*2026-05-03, branch `claude/run-b-modis`. Six checkpoints reached; two
checkpoints (3 and 4) blocked on MODIS pre-flight failure. Working tree
clean, all commits pushed.*

## What to look at first when you wake up

1. **`data/outputs/RUN_B_BLOCKERS.md`** — the MODIS acquisition story
   end-to-end. Earth Engine, LP DAAC, AWS-mirrored MODIS, NEO and
   AppEEARS are all unauthenticated-rejected in this sandbox; the
   user's preamble warned this would happen. The file lists three
   ways the user can unblock the run from their side
   (push the GEE-exported TIFFs, drop a service-account JSON, or
   add an Earthdata `.netrc`).
2. **`data/outputs/koppen_stratification.md`** — substitute biome
   stratification using climate zones (computable without MODIS).
   **Within-zone transfer is *worse* than the cross-zone baseline in
   both qualifying zones**; Köppen D's CI is significantly negative.
   This is a stronger framing-2 result.
3. **`data/outputs/methodology_evolution_panel.png`** (and `_screen.png`) —
   2×3 panel showing F, B, MODIS placeholder, Köppen C, Köppen D, and
   a narrative caption. The MODIS-pending pane is honestly labelled.

## Headline numbers (no new model training; v1 numbers re-confirmed)

| Config | Features | Transfer R² | 95% CI | CI excludes 0? |
|---|---:|---:|---|---|
| F: climate-only (8 bioclim) | 8 | **+0.127** | (+0.019, +0.216) | yes |
| B: full features (20) | 20 | +0.020 | (−0.141, +0.146) | no |
| F+NPP (12) | — | **[PENDING MODIS]** | — | — |
| Full+MODIS (25) | — | **[PENDING MODIS]** | — | — |
| Köppen C (within-zone F) | 8 | −0.336 | (−1.06, +0.04) | no (spans 0) |
| Köppen D (within-zone F) | 8 | −0.199 | (−0.39, −0.06) | yes (significantly NEGATIVE) |

## Did the relaxation help / did F+NPP beat F?

- **MODIS-blocked. F+NPP is not yet trained.** When MODIS lands, the
  user can re-run from Checkpoint 3. The infrastructure is in place
  — `src/features.py`'s `default_registry()` already lists `npp`,
  `lst_day`, `lst_night`, `landcover`, and the engineered
  `lst_diurnal_range` feature. Once the rasters are in
  `data/raw/modis/` the existing `src/extract_features_real.py` will
  pick them up automatically.

## Did MODIS rescue the full-features model?

- **MODIS-blocked.** Same answer.

## Did stratification close the transfer gap?

- **No, and the substitute Köppen-Geiger climate-zone test makes the
  failure more concrete.** Both Köppen C (n_us=89) and Köppen D
  (n_us=159) had within-zone transfer R² *below* the cross-zone
  baseline of +0.127. Köppen D's CI is fully below zero, meaning the
  zone-trained model on continental sites does worse than predicting
  the US-mean *Rs*.
- Why: the cross-zone F transfer R² of +0.127 is carried by the
  cross-zone precipitation gradient, which the SHAP analysis already
  identified as the only stable cross-region signal. Stratifying
  removes that gradient and what remains has too little signal to
  generalise.
- The IGBP-stratified test is still worth running once MODIS lands,
  because land-cover stratification (forest-only, cropland-only) tests
  a different hypothesis — that the land-use confound is what breaks
  cross-region transfer of soil features. The Köppen result lowers the
  prior on stratification rescuing transfer, but does not refute the
  IGBP-specific test.

## Checkpoints completed (this run)

| Checkpoint | Status | Output |
|---|---|---|
| Branch setup | ✅ | claude/run-b-modis pushed; Run A artefacts brought across via `git checkout claude/continue-mshi-geo-V3cuc -- ...` |
| 1 (parquets) | ✅ | training_features regenerated from existing respiration_points (smoke-test corruption from synthetic demo cleared); raw rasters survived; full Checkpoint-1 download pipeline unnecessary |
| 2 (MODIS) | ❌ → 📝 | unrecoverable in this environment; documented in RUN_B_BLOCKERS.md |
| 3 (re-extract w/ MODIS) | 🔒 blocked on 2 | — |
| 4 (F+NPP, Full+MODIS) | 🔒 blocked on 3 | — |
| 5 (biome stratification) | ✅ via substitute | Köppen-Geiger zones; data/outputs/koppen_stratification.{json,md} |
| 6 (heroes + evolution panel) | ✅ partial | data/outputs/methodology_evolution_panel.png with [PENDING MODIS] placeholder pane; framing2_comparison_panel NOT updated (would require F+NPP) |
| 7 (paper + summary) | ✅ | paper_results_draft.md updated with §4.5 Köppen section + [PENDING MODIS] tags; RUN_B_SUMMARY.md (this file) |

## Things worth flagging for the user

1. **The cross-zone F transfer R² of +0.127 is the dominant honest
   number from Run B.** The Köppen test argues that this number is
   *not* a noise floor that stratification could improve through.
   Adding NPP is the highest-priority remaining lever, and the framing-2
   pitch holds even before NPP arrives.
2. **The smoke-test (`bash run.sh demo`) overwrites
   `data/processed/training_features.parquet`** with synthetic
   3000-row data because `demo_synthetic.py` writes to the same path.
   This bit Run B Checkpoint 1 (had to re-extract real point features
   before any analysis). Recommend the demo be hardened to write to
   `data/processed/training_features_demo.parquet` (a one-line change
   in `src/demo_synthetic.py`). Not done in this run since out of
   scope, but flagged.
3. **The `framing2_comparison_panel.png` was not updated** to use
   F+NPP as the climate-features reference, because that swap requires
   F+NPP which is MODIS-blocked. The existing Run-A panel is correct
   and present.

## Three open questions for the user

1. **MODIS re-acquisition path:** which of the three unblock paths in
   `RUN_B_BLOCKERS.md` is easiest for you (run the GEE export on your
   laptop and push, drop a service account JSON, or set up an
   Earthdata `.netrc`)? If GEE export, the script in your Run B
   preamble is already correct.
2. **Köppen B (arid) had Asia n=51 / US n=24 — close to the
   thresholds.** Want me to drop the threshold to 40/20 in a future
   run and include B even with the wider CI? Arid-zone results would
   address the Indo-Gangetic Plain / Iranian Plateau hotspots
   visible in the hero maps. Yes/no/wait-for-MODIS.
3. **Pitch framing.** The Köppen-stratification negative result
   strengthens the framing-2 story: the transfer ceiling at +0.127 is
   the cross-zone precipitation gradient, and no obvious slicing of
   the data improves it. Do you want me to push that framing more
   forcefully in the paper draft (currently I added it to §4.5 and
   §6 but it's still cautious about the IGBP-pending test)?

## File-tree of what landed in this run

```
data/outputs/RUN_B_BLOCKERS.md
data/outputs/RUN_B_SUMMARY.md            (this file)
data/outputs/koppen_stratification.json
data/outputs/koppen_stratification.md
data/outputs/methodology_evolution_panel.png
data/outputs/methodology_evolution_panel_screen.png
data/outputs/paper_results_draft.md      (updated with §4.5 + [PENDING MODIS] tags)

scripts/checkpoint5_koppen.py
scripts/checkpoint6_panel.py
```

Branch `claude/run-b-modis` will be at the Checkpoint-7 commit after
this file is pushed. To resume Run B once MODIS arrives, run from this
branch:

```bash
source venv/bin/activate
# (drop MODIS rasters into data/raw/modis/ first)
python src/extract_features_real.py --config configs/mshi_geo.yaml
# then run a Checkpoint-4 script that adds F+NPP and Full+MODIS to
# sweep_results_v2.json — the analogue of scripts/task2_sweep.py with
# the new feature lists. I can write that script in advance if you'd
# like; it would be ~80 lines and would only fail on the missing
# rasters until they land.
```
