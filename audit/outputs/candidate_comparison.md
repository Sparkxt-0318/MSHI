# Three candidate contributions: comparison and recommendation (2026-11-10)

All numbers come from the scripts in `audit/` (full tables: `audit/outputs/tables.md`). Primary
variant `strict` (annual coverage = 1); `incl_missing` (coverage 1 or missing) in brackets where it
differs. R2 is on log Rs; intervals are 95% bootstrap intervals over test sites (2000 resamples).

| | A1 Continent transfer matrix | A2 Ceiling on explainable variance | A3 SRDB coordinate errors |
|---|---|---|---|
| **Main finding** | Climate-only Rs models transfer between continents only where the training continent's climate covers the test continent; here only Asia does, every other cross-continent pair is at or below zero or unresolved, and Europe has no skill even internally. | About a third of site-level variance in annual log Rs is disagreement between studies and plots inside a 0.05-degree cell that no gridded predictor can explain; where climate models work they capture only a quarter to two fifths of the rest. | 2.1% of SRDB records with coordinates disagree with their Country field, 41 of them clear errors with a fix that SRDB's checks cannot catch, but they barely change model skill. |
| **Key numbers** | AS->NA OLS log P 0.20 [0.11, 0.27], XGBoost 0.20 [0.10, 0.28] (incl_missing 0.26, 0.29); NA->AS 0.03 [-0.14, 0.17] OLS, -0.14 [-0.29, -0.02] XGBoost; within NA 0.25 [0.15, 0.34], AS 0.16 [0.06, 0.24], EU -0.08 [-0.12, -0.05]; XGBoost minus OLS log P for AS->NA -0.005 [-0.067, 0.050]; rho(XGBoost R2, mean DI) -0.80 (-0.58), descriptive; NPP adds +0.02-0.03 (lower bounds >= 0.006) for AS->NA only. | Within-cell disagreement: different studies 0.168 [0.127, 0.215] vs same study 0.080 (same year) and 0.043 (different years); nested between-study variance 0.103 [0.064, 0.146]; ceiling 0.663 [0.548, 0.759] (0.672); share of ceiling reached: AS->NA 0.30 [0.16, 0.43], within NA 0.38 [0.24, 0.55], within AS 0.24 [0.11, 0.37], Europe < 0. | 284 of 13,772 records (86 studies) flagged: 41 high (17 studies), 86 medium, 157 low; 190 of 284 (29 of 41 high) lie on land in another country; 26 of 284 (0 of 41 high) are in SRDB's own low-land list; 81 would have entered the models; transfer R2 changes <= 0.016 (OLS), <= 0.03 for fixed-hyperparameter XGBoost except one flexible-model pair (0.09). |
| **Prior work** | No Rs or Rh study found that holds out a continent or region or reports a transfer matrix (about 400 open-access full texts screened plus targeted reads); validation in the field is random k-fold, leave-one-out, leave-one-site-out or site-grouped. The design itself is established outside Rs (Ploton 2020; Meyer & Pebesma 2021, 2022; Roberts 2017; Ludwig 2023), and Meyer & Pebesma 2022 call for accuracy by continent. Several Rs methods sections were unreadable [UNVERIFIED]. | No study found that uses replicated records within grid cells to bound R2 for Rs or any land-flux upscaling. Nearest: Bahn 2010 (cross-site vs within-site error), Rammig 2018 (within-pixel variability; abstract only), replicate eddy-covariance towers (Oren 2006; Hill 2017), noise ceilings in other fields (Li 2021; Lage-Castellanos 2019). Jian 2018 and Bond-Lamberty & Thomson 2010 full texts not read [UNVERIFIED]. | The tests are standard in biodiversity data cleaning (Yesson 2007; Zizka 2019; Robertson 2016; Ribeiro 2022). SRDB fixes coordinates piecemeal (51 sign flips and 38 swaps across its git history) and has open issues #50 and #134; no published audit of SRDB or COSORE coordinates and no erratum. |
| **Robustness** | AS->NA positive in both variants, across the 10 best tuning configurations (0.195-0.210; 0.254-0.289) and every flagged-record policy. XGBoost values for North American and European sources vary by up to 0.6 across configurations; Africa and Oceania have 27-35 test sites; the coverage-skill association is weaker in incl_missing. | "Ceiling well above observed skill" holds under every estimator; the ceiling value depends on the noise model (nested 0.66, pair-weighted 0.80, one-way 0.86, semivariogram 0.71) and assumes replicated cells (60% of cells) represent all cells; Africa and Oceania ceilings unstable; IRGA vs alkali has 8 cells. | The 41 high-confidence errors were stable through every rule change in review; low-confidence counts move with the 10/50 km tolerances; effect on models small under all policies. |
| **What it adds** | Tests the paper's own premise and replaces "Asia-to-US transfer works" with a general, falsifiable statement (transfer needs climate coverage). Gives the Rs community a continent-level evaluation it does not have. | A yardstick for every R2 in the paper: rules out noisy targets as the reason for weak transfer and quantifies headroom; suggests that random-split R2 of 0.76-0.79 in recent SRDB machine-learning papers exceed what independent sites allow (targets differ, so not proven). | Data-quality appendix, a cleaned site table, and a ready contribution to SRDB (draft issue). Strengthens the methods; does not change conclusions. |

## Recommendation

**Lead with A1, the continent transfer matrix, and make A2, the ceiling, the second main-text
result. Put A3 in the supplementary material, with the SRDB issue filed separately. None of the three
should be dropped, but several claims inside them should be:** single-value XGBoost results for
non-Asian training continents (they swing by up to 0.6 across equally good configurations), the
IRGA vs alkali comparison (8 cells), R2-to-ceiling fractions for Africa and Oceania (unstable), and
any comparison of MODIS-run numbers with the main matrix (different test sets).

Reasons:

1. A1 answers the question the study was built on. Its one robust positive result, Asia to North
   America, survives every check (both coverage variants, the ten best tuning configurations, every
   flagged-record policy). It is explained by something general and testable: how much of the test
   continent's climate the training continent covers. The reverse direction, Europe, and Oceania
   fail in a way that the same explanation predicts.
2. No soil-respiration study found holds out a continent, so A1 fills a gap the methods literature
   explicitly asks to fill, while using a design reviewers already accept.
3. A2 is probably the more original idea, but it works best as the frame for A1. It turns "R2 = 0.2"
   into "a third of what is achievable at this resolution", and it pre-empts the obvious objection
   that the data are too noisy to transfer. Alone, its headline number hinges on a noise model and
   on replicated cells being representative, and it does not answer the transfer question.
4. A3 is solid and useful to the community, but the errors it finds change transfer skill by at
   most a few hundredths for the stable models, so it cannot carry a paper.

**Strongest argument against this choice.** A1 applies a standard technique to a new variable, and
its main message is negative and arguably expected: models do not extrapolate outside the climate
they were trained on. Its only positive result is modest (R2 0.20-0.29), is matched by a
one-variable regression on precipitation, partly rests on test sets of 27-35 sites, and its
coverage-skill association weakens in the incl_missing variant (rho -0.58). A2, by contrast, has
no precedent found in soil respiration or land-flux upscaling and is reusable by every group that
maps Rs. If a hand check of the Jian et al. 2018 and Bond-Lamberty & Thomson 2010 full texts
confirms that neither estimates a replicate-based ceiling, leading with A2 and using A1 as its
application is a defensible alternative.
