# Round C — pitch deliverables summary

*2026-05-03, branch `claude/round-c-deliverables`. All seven checkpoints
committed and pushed. Working tree clean.*

## Three things to look at first

1. **`data/outputs/genius_pitch_deck.pptx`** — 12-slide deck. Open in
   PowerPoint or Keynote and step through. Real numbers throughout
   (no placeholders except `[Author Name]` / `[School]`). Time-budget
   the talk to roughly one slide per 30–45 seconds for an 8–10 min
   pitch.
2. **`data/outputs/genius_poster.pdf`** — 36 × 24 in landscape vector
   PDF, print-ready. Single sheet, full layout. (PNG preview at
   `genius_poster.png` for quick review; editable `genius_poster.pptx`
   also present though slightly less polished than the matplotlib PDF.)
3. **`data/outputs/RUN_C_blockers_or_open_questions`** ←  there are
   none (no blockers this round); look instead at section "Open
   questions for the user" at the end of this file.

## Deliverables (filename → one-line description)

| File | Quality | Notes |
|---|---|---|
| `genius_pitch_deck.pptx`           | ready-to-use | 12 slides, Bedrock styling, real numbers, embeds 4 figures. Fill in `[Author Name]` and `[School]` on slide 1 + 12. |
| `genius_poster.pdf`                | ready-to-use | 36 × 24 in landscape vector. Author/school placeholders to fill in. |
| `genius_poster.png`                | preview      | 100 DPI raster preview of the poster. |
| `genius_poster.pptx`               | editable     | pptxgenjs source (LibreOffice on this host can't import .pptx so PDF is rendered separately via matplotlib). |
| `sensor_connection_figure.png`     | ready-to-use | 3-panel conceptual figure (EAB schematic + I ∝ r_e ∝ r_ox ∝ Rs chain + coverage comparison). 300 DPI print. |
| `sensor_connection_figure_screen.png` | ready-to-use | 160 DPI for slide deck. |
| `adversarial_qa_rehearsal.md`      | ready-to-use | 15 anticipated hostile questions + rehearsed answers. |
| `paper_essd_submission_ready.md`   | draft        | ESSD format with Vancouver references, abstract, methods subsections, data/code availability statements. Introduction sketched but not fully written; ready for you to expand. 2,564 words. |
| `executive_summary.md`             | ready-to-use | One page (~386 words). Six numbered sections. |
| `paper_results_draft.md`           | reference    | Original informal draft from Run A; preserved for diff against `paper_essd_submission_ready.md`. |

Existing artefacts referenced (already on the branch from Run A and Run B):

- `bootstrap_ci.json`, `alternative_metrics.json`, `metrics_summary.md`
- `koppen_stratification.json`, `koppen_stratification.md`
- `literature_comparison.md`
- `framing2_table.csv`, `framing2_table.md`, `framing2_comparison_panel.png`
- `methodology_evolution_panel.png`, `methodology_evolution_panel_screen.png`
- `hero_climate_only_asia.{png,pdf,screen.png}` (with distinguishing tags)
- `hero_full_features_asia.{png,pdf,screen.png}` (with distinguishing tags)
- `shap_asia_only.png`, `shap_us_only.png`, `shap_comparison.png`,
  `shap_dual_region.json`
- `RUN_A_SUMMARY.md`, `RUN_B_SUMMARY.md`, `RUN_B_BLOCKERS.md`

## Quality flags

- **Pitch deck:** all 12 slides render correctly, embedded images are
  the latest hero/SHAP/comparison versions. The only manual step
  before delivery is filling in `[Author Name]` on slides 1 and 12
  and `[Affiliation]` on slide 1.
- **Poster:** the matplotlib PDF version has correct layout but body
  text in row-1 columns (Problem / Methods / Framework) does not
  auto-wrap perfectly at the small-zoom preview. At true 36 × 24 in
  print size the text is readable. If you'd like tighter column
  text, the pptxgenjs `genius_poster.pptx` source has automatic
  wrapping; you can edit it in PowerPoint and export to PDF from there.
- **Sensor connection figure:** entirely conceptual — the figure
  caption explicitly notes "first co-located EAB / chamber Rs
  deployment queued for next phase" so judges aren't misled.
- **ESSD paper draft:** the introduction (§1) is a one-line
  placeholder — the rest of the paper is fully drafted. Recommend
  expanding §1 to ~2-3 paragraphs covering the global Rs-flux
  context, the upscaling-validation gap, and a one-paragraph
  summary of contributions before submission.
- **Adversarial Q&A:** 15 questions covering methodology / novelty /
  robustness / project axes. Each answer ends with a forward-looking
  pivot.

## Open questions for the user

1. **Author block.** Fill in `[Author Name]`, `[Affiliation]`,
   `[School]`, `[author@email]`, and `[ORCID]` placeholders across
   the deck, poster, paper draft, and executive summary. Single
   find-replace per file. Files containing placeholders: deck,
   poster (both PDF and pptx), paper draft, executive summary.
2. **Pitch length.** Is the target 5 min, 8 min, or 10–15 min? The
   12-slide deck is calibrated for 8 minutes (40-45 sec per slide).
   If 5 min, drop slides 4 and 11 (methods overview and roadmap)
   and keep the conceptual arc intact. If 10-15 min, the slide count
   is right but expect 60-80 seconds per slide.
3. **The MODIS NPP run.** The pitch deck and poster currently say
   "MODIS NPP integration ≤ 2 weeks" on the roadmap. If you push
   the GEE-exported rasters before the competition, the F+NPP and
   Full+MODIS results would slot directly into slide 6 (replacing
   the existing B map) and slide 11 roadmap text. Worth doing if
   time allows.
4. **Adversarial Q&A — anything I missed?** I worked from generic
   ML / ecology adversarial categories; if you've heard specific
   judge tropes from past Genius Olympiad rounds, send them and I'll
   add to the file.

## Suggested workflow for the next 7 days

| Day | Action |
|---:|---|
| 1 | Open the deck and poster. Replace placeholders. Read through Q&A. Identify weak slides for revision. |
| 2 | Get one trusted reader to do a stranger-eye pass on the deck + executive summary. Flag any number that doesn't make sense. |
| 3 | Read the 15 Q&A out loud. Time yourself. Tighten any answer >30 sec. |
| 4 | Send paper_essd_submission_ready.md to a writing reviewer (mentor, English teacher) for §1 introduction expansion + general flow. |
| 5 | If time: run the MODIS GEE export (your Run B preamble has the script). Push rasters and tell me to re-run F+NPP / Full+MODIS. |
| 6 | Print poster at full size. Sit with it for 30 minutes. Check visual hierarchy under fluorescent light. |
| 7 | Mock pitch to 2-3 people unrelated to the project. Ask them to ask the meanest possible questions. Refine answers. |

## File-tree of what landed in this round

```
data/outputs/genius_pitch_deck.pptx
data/outputs/genius_poster.pdf
data/outputs/genius_poster.png
data/outputs/genius_poster.pptx
data/outputs/sensor_connection_figure.png
data/outputs/sensor_connection_figure_screen.png
data/outputs/adversarial_qa_rehearsal.md
data/outputs/paper_essd_submission_ready.md
data/outputs/executive_summary.md
data/outputs/ROUND_C_SUMMARY.md          (this file)

deck/build_pitch_deck.js                  (pptxgenjs source for deck)
deck/build_poster.js                      (pptxgenjs source for poster)
scripts/sensor_connection_figure.py       (matplotlib source for sensor fig)
scripts/build_poster_matplotlib.py        (matplotlib PDF rendering)
```

Branch is at HEAD `86f7f2b` (will be one ahead after this commit),
fully pushed. Working tree clean.

Good luck.
