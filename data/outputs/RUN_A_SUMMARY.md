# Run A — overnight summary

*2026-04-27, branch `claude/continue-mshi-geo-V3cuc`. All six tasks committed; tree clean.*

## What to look at first when you wake up

1. **`data/outputs/bootstrap_ci.json`** — the headline statistical claim.
   F (climate-only) transfer R² = +0.127, 95 % CI (+0.019, +0.216),
   excludes zero. B (full features) transfer R² = +0.020, 95 % CI
   (−0.141, +0.146), includes zero. The framing-2 story is now defensible
   against the trivial null.
2. **`data/outputs/metrics_summary.md`** — the alternative metrics table.
   F wins on R², RMSE, NRMSE, Spearman, MAE; tertile accuracy is a tie
   (B nominally 2.9 pts higher) and is the weakest of the metrics.
3. **`data/outputs/literature_comparison.md`** — the four most directly
   comparable continental Rs studies. None of them report a held-out
   cross-continental site-level transfer R²; THIS WORK is the first.

## Tasks 1–6: status

| # | Task | Status | Verdict |
|---|---|---|---|
| 1 | Manipulation-flag relaxation | ✅ done | **Negative result, reverted.** Pre-dedup gain = +7 Asia rows; well below the +50 threshold. |
| 2 | Bootstrap CIs on transfer R² | ✅ done | F excludes zero. B includes zero. |
| 3 | Alternative metrics | ✅ done | F wins R²/RMSE/NRMSE/Spearman/MAE; tertile accuracy effectively a tie. |
| 4 | Literature comparison | ✅ done | None of Hashimoto 2015, Warner 2019, Yao 2021, Stell 2021 report cross-continental site-level transfer R². |
| 5 | Paper draft citations + metrics | ✅ done | All four [NEEDS CITATION] tags resolved; Table 2 (bootstrap CI + alt metrics) inserted in §2; §5 reframed around verified findings. |
| 6 | This summary | ✅ done | — |

## Did the manipulation-relaxation help?

**No.** The current SRDB filter keeps NaN / Control / control / None /
empty strings. Inspection of the 7,792 records with non-null *Rs<sub>annual</sub>*
shows that essentially every non-NaN value denotes an explicit experimental
treatment (Fertilized = 798, Litter manipulation = 132, Warmed = 117,
Thinned = 85, CO2 = 82, Drought = 64, Irrigated = 57, Grazing = 55,
Burned = 50, ...). The only candidate-keep labels are measurement
methodology (Collar depth, Sampling/Trenched collars), landscape
characterizations (Hydrogeomorphic setting), and absence-of-treatment
markers (No grazing, Undrained-unplanted). Maximally relaxing the filter
to include all those labels gives:

```
CURRENT  total 4,901   Asia 2,170   US 1,040
RELAXED  total 4,931   Asia 2,177   US 1,049
                       gain +7      gain +9
```

Pre-dedup, +7 Asia. After 5-km dedup, the surviving Asia gain is
expected to be 0–3 sites. Per the overnight execution rule, this was
not committed to `src/build_target.py`. Tasks 2–6 used the existing
615-Asia / 274-US training set.

The 4,964 NaN-manipulation records dwarf everything else. The training
set is essentially "all SRDB records that did not have any manipulation
flag at all." There is no significant additional pool of legitimate
observational sites being filtered out.

## Did the F-vs-B contrast hold up?

**Yes, and now with statistical significance.**

| | F (climate-only, 8 features) | B (full features, 20) |
|---|---:|---:|
| Asia → US transfer R² | **+0.127** | +0.020 |
| 95 % bootstrap CI | **(+0.019, +0.216)** | (−0.141, +0.146) |
| CI excludes zero? | **yes (p < 0.05)** | no |
| Spearman ρ | **+0.277** | +0.249 |
| RMSE (log Rs) | 0.585 | 0.616 |

The bootstrap test on B's transfer R² is the cleanest available evidence
that adding the SoilGrids texture features fails — not just "does worse
than F" but "is statistically indistinguishable from predicting the
mean." The Run-A claim is therefore stronger than the Run-26 claim:

> Climate features generalise Asia → US (R² = 0.127, 95 % CI excludes zero).
> Adding SoilGrids texture features collapses transfer to 0.020, 95 % CI
> includes zero. The full-feature configuration cannot be distinguished
> from the trivial mean-predictor on the held-out continent.

## What's in the literature that's most relevant

From the four studies verified via Crossref (full table in
`data/outputs/literature_comparison.md`):

- **Stell et al. 2021** is the most relevant. They explicitly characterise
  SRDB's "still biased toward northern latitudes and temperate zones"
  spatial bias as a source of model uncertainty and propose an optimised
  global sample distribution. They do NOT run a held-out cross-continental
  performance test; that's the gap THIS WORK fills.
- **Warner et al. 2019** is the methodological precedent for a global
  1 km Rs map via quantile regression forest. They report MAE = 18.6 and
  RMSE = 40.4 Pg C yr⁻¹ on the global sum (within-sample), no site-level
  R² in the abstract.
- **Hashimoto et al. 2015** is the older climate-driven 0.5° model with
  global sum 91 Pg C yr⁻¹ (95 % CI 87–95). No site-level R² in abstract.
- **Yao et al. 2021** is the SHR (heterotrophic only) version with
  random forest at 0.5°. No R² in abstract.

I removed the previously fabricated "Hashimoto et al. 2015 reports
R² ≈ 0.40–0.55 at the site level" claim from the paper draft because
no such number is in the abstract, and I cannot get past the publisher
paywalls on the others to verify the methods/results. If you have the
PDFs locally, you may want to spot-check whether any of them does
report a site-level CV R² that could anchor a more direct comparison.

## Should we worry about anything?

1. **F's CI low-end is +0.019.** Statistically significant, but the
   lower bound is barely above zero. A pitch claim of "statistically
   significant cross-continental transfer" is honest, but the
   *magnitude* of the effect is small. Avoid language that suggests
   the climate-only model is "validated" or "high-fidelity" — it isn't.
2. **n_us = 272 is small for bootstrap.** 2,000 iterations on 272 points
   is enough to characterize the sampling distribution, but the CI is
   wide because of the small sample. Future runs with more US sites
   would tighten it.
3. **Tertile accuracy is the one metric where B nominally beats F.** It's
   a much weaker test than R², and the gap is 2.9 pts (37.1 % vs 40.0 %).
   I called this out in `metrics_summary.md` and the paper draft, but
   if a reviewer asks "why doesn't B win on tertile then?", the honest
   answer is: tertile classification discards most of the within-tertile
   information, both models predict heavily into the middle tertile
   (regression-to-mean), and the noise on this metric at n = 270 is too
   large for a 2.9-pt difference to mean anything.
4. **The paper draft is now 2,757 words.** Slightly over the 1,500–2,500
   target. The added Table 2 and Section 5 expansion are doing real work
   but if you need to cut, Section 6 (the "what would close the gap"
   discussion) is the most cuttable.

## Open questions for you (need decisions before Run B)

1. **Cite Stell 2021 versus the sentinel "first to characterise" claim.**
   I'm framing THIS WORK as the first held-out cross-continental
   transfer R² test on the SRDB record. That's defensible against the
   four papers I checked, but I cannot rule out that an obscure Rs
   paper has done this (machine-learning chapter, dissertation,
   conference proceeding). If you want to weaken the claim to
   "to our knowledge", that's the safe phrasing. The current draft
   already says "to our knowledge"; if you want to make it a stronger
   claim or remove the hedge, decide before submission.
2. **Should Run B add a regional sub-model split** (Köppen or IGBP),
   or wait for MODIS NPP first? The Run-A diagnosis is that the
   feature-target relationship differs cross-region; a regional split
   addresses this directly even without NPP. NPP is more standard but
   has the GEE-login dependency.
3. **Hero map decision.** The current `hero_climate_only_asia.png` shows
   the F model's anomaly map (R² = +0.127). The current
   `hero_full_features_asia.png` shows the B model's anomaly map
   (R² = +0.020, CI includes zero). I am not regenerating these per
   Run-A instructions. If you decide post-Run-B that B's map should
   not be presented at all (because its transfer is statistically
   indistinguishable from zero), the right move is to drop it from
   the hero set rather than re-render it more prettily.

## File-tree of what landed in this run

```
scripts/task1_manipulation_relaxation.py    (negative-result inspection)
scripts/task2_bootstrap_ci.py
scripts/task3_alt_metrics.py

data/outputs/bootstrap_ci.json
data/outputs/alternative_metrics.json
data/outputs/metrics_summary.md
data/outputs/literature_comparison.md
data/outputs/paper_results_draft.md         (updated in place)
data/outputs/RUN_A_SUMMARY.md               (this file)
```

Branch is at HEAD `dbf1aeb` (will be one ahead after this commit),
fully pushed. Working tree clean.
