# Three candidate contributions: comparison and recommendation (2026-11-10)

All numbers come from the scripts in `audit/` (full tables: `audit/outputs/tables.md`). Primary
variant `strict` (annual coverage = 1); `incl_missing` (coverage 1 or missing) in brackets where it
differs. R2 is on log Rs; intervals are 95% bootstrap intervals over test sites (2000 resamples).

| | A1 Continent transfer matrix | A2 Ceiling on explainable variance | A3 SRDB coordinate errors |
|---|---|---|---|
| **Main finding** | Transfer between continents is weak and depends on direction and model. North America is predictable from Asia with every model (R2 about 0.2), and from Europe with linear climate models only; Asia is predictable from neither. XGBoost fails wherever the test climate lies outside the training climate; one- or two-variable linear models degrade more gracefully. Europe has no skill within itself. | About a third of site-level variance in annual log Rs is disagreement between studies and plots inside a 0.05-degree cell that no gridded predictor can explain; where climate models work they capture only a quarter to two fifths of the rest. | 2.1% of SRDB records with coordinates disagree with their Country field, 41 of them clear errors with a fix that SRDB's checks cannot catch, but they barely change model skill. |
| **Key numbers** | AS->NA OLS log P 0.20 [0.11, 0.27], XGBoost 0.20 [0.10, 0.28] (incl_missing 0.26, 0.28); EU->NA OLS MAT + log P 0.24 [0.12, 0.34], OLS log P 0.11 [0.02, 0.18], XGBoost -0.05 (XGBoost minus MAT + log P -0.30 [-0.40, -0.19]); NA->AS 0.03 [-0.14, 0.17] OLS, -0.14 [-0.29, -0.02] XGBoost; within NA 0.25 [0.15, 0.34], AS 0.16 [0.06, 0.24], EU -0.07 [-0.12, -0.05]; XGBoost minus OLS log P for AS->NA -0.005 [-0.067, 0.050]; rho with coverage, descriptive: XGBoost R2 vs mean DI -0.80 (-0.58), OLS log P R2 vs range share 0.18 (0.11); NPP adds +0.02-0.03 (lower bounds >= 0.006) for AS->NA only. | Within-cell disagreement: different studies 0.168 [0.127, 0.215] vs same study 0.080 (same year) and 0.043 (different years); nested between-study variance 0.103 [0.064, 0.146]; ceiling 0.663 [0.548, 0.759] (0.672); share of ceiling reached: AS->NA 0.30 [0.16, 0.43], within NA 0.38 [0.24, 0.55], within AS 0.24 [0.11, 0.37], Europe < 0. | 284 of 13,772 records (86 studies) flagged: 41 high (17 studies), 86 medium, 157 low; 190 of 284 (29 of 41 high) lie on land in another country; 26 of 284 (0 of 41 high) are in SRDB's own low-land list; 81 would have entered the models; transfer R2 changes <= 0.016 (OLS), <= 0.03 for fixed-hyperparameter XGBoost except one flexible-model pair (0.09). |
| **Prior work** | No Rs or Rh study found that holds out a continent or reports a transfer matrix (about 400 open-access full texts screened plus targeted reads). An adversarial refuter (79 searches, about 94 more full texts) found no counterexample for continents. It did find a regional one: Liu L 2024 held out tower groups and a US state, for Reco/NEE in the US Midwest. So the claim must say "continent", not "region". Rs validation is random k-fold, leave-one-out, leave-one-site-out or site-grouped. Two recent papers handle SRDB's spatial clustering by weighting or pruning, not hold-out (Jiang 2025; Cao 2026), and must be cited. The design is established outside Rs (Ploton 2020; Meyer & Pebesma 2021, 2022; Roberts 2017; Ludwig 2023), and Meyer & Pebesma 2022 call for accuracy by continent. Validation sections of Jiang 2025, Gomes 2026 and several older products unreadable [UNVERIFIED]. | No Rs study found that uses replicate records sharing a cell or site to bound R2. An adversarial refuter (75 searches) found none either, but the method exists in other fields: noise-corrected r2 for satellite estimates (Lobell 2021) and pixel-to-plot corrections for vegetation models (Rammig 2018; abstract only). The novelty is therefore the Rs application, not the method. Nearest Rs work: Bahn 2010 (cross-site error vs literature within-site error, no R2 bound). Studies that quantify within-site noise without bounding skill: Lavoie 2015, Cai 2023, Giasson 2013. Also replicate eddy-covariance towers (Oren 2006; Hill 2017) and noise ceilings elsewhere (Li 2021; Lage-Castellanos 2019). Jian 2018, Bond-Lamberty & Thomson 2010 and several product methods unreadable [UNVERIFIED]. | The tests are standard in biodiversity data cleaning (Yesson 2007; Zizka 2019; Robertson 2016; Ribeiro 2022). SRDB fixes coordinates piecemeal (51 sign flips and 38 swaps across its git history) and has open issues #50 and #134; no published audit of SRDB or COSORE coordinates and no erratum. |
| **Robustness** | AS->NA positive for every model in both variants, across the 10 best tuning configurations (0.195-0.210; 0.254-0.289) and every flagged-record policy. EU->NA positive for both linear models in both variants. XGBoost values for North American and European sources vary by up to 0.6 across configurations; Africa and Oceania have 27-35 test sites. The coverage-skill association holds for XGBoost only and is weaker in incl_missing. | "Ceiling well above observed skill" holds under every estimator; the ceiling value depends on the noise model (nested 0.66, pair-weighted 0.80, one-way 0.86, semivariogram 0.71) and assumes replicated cells (60% of cells) represent all cells; Africa and Oceania ceilings unstable; IRGA vs alkali has 8 cells. | The 41 high-confidence errors were stable through every rule change in review; low-confidence counts move with the 10/50 km tolerances; effect on models small under all policies. |
| **What it adds** | Tests the paper's own premise and replaces "Asia-to-US transfer works" with a falsifiable, model-specific statement: flexible models need the test climate inside the training climate, while simple monotone climate models transfer weakly but more widely. Gives the Rs community a continent-level evaluation it does not have. | A yardstick for every R2 in the paper: rules out noisy targets as the reason for weak transfer and quantifies headroom; suggests that random-split R2 of 0.76-0.79 in recent SRDB machine-learning papers exceed what independent sites allow (targets differ, so not proven). | Data-quality appendix, a cleaned site table, and a ready contribution to SRDB (draft issue). Strengthens the methods; does not change conclusions. |

## Recommendation

**Lead with A1, the continent transfer matrix, and make A2, the ceiling, the second main-text
result. Put A3 in the supplementary material, with the SRDB issue filed separately. None of the three
should be dropped, but several claims inside them should be:** single-value XGBoost results for
non-Asian training continents (they swing by up to 0.6 across equally good configurations), the
IRGA vs alkali comparison (8 cells), R2-to-ceiling fractions for Africa and Oceania (unstable),
any comparison of MODIS-run numbers with the main matrix (different test sets), and any statement
that only Asia transfers or that climate coverage explains transfer for all models (both hold for
XGBoost only).

Reasons:

1. A1 answers the question the study was built on. Its one result that holds for every model,
   Asia to North America, survives every check (both coverage variants, the ten best tuning
   configurations, every flagged-record policy). For XGBoost, skill follows how much of the test
   continent's climate the training continent covers (rho -0.80). The reverse direction, Europe as
   a source and Oceania all fail, as that coverage predicts. Linear models trained on Europe still
   predict North America (MAT + log P 0.24 [0.12, 0.34], where XGBoost scores -0.05). The general
   lesson is therefore about model flexibility and extrapolation, which is more useful to groups
   mapping Rs than a single working pair.
2. No soil-respiration study found holds out a continent, and an adversarial search did not find
   one either. A1 fills a gap the methods literature explicitly asks to fill, using a design
   reviewers already accept. Recent papers recognise that SRDB's clustering biases Rs maps
   (Jiang 2025; Cao 2026) but correct it by reweighting instead of testing transfer, so the question
   is current.
3. A2 is new for soil respiration, but the adversarial search found the same method in remote
   sensing (Lobell 2021) and vegetation-model evaluation (Rammig 2018), so it is new as an
   application, not as a method. It works best as the frame for A1. It turns "R2 = 0.2" into "a
   third of what is achievable at this resolution", and it pre-empts the obvious objection that the
   data are too noisy to transfer. Alone, its headline number hinges on a noise model and on
   replicated cells being representative, and it does not answer the transfer question.
4. A3 is solid and useful to the community, but the errors it finds change transfer skill by at
   most a few hundredths for the stable models, so it cannot carry a paper.

**Strongest argument against this choice.** A1 applies a standard technique to a new variable, and
its main message is negative and arguably expected: flexible models do not extrapolate outside the
climate they were trained on. Its positive results are modest (R2 0.20-0.30) and are matched or
beaten by one- or two-variable linear regressions. Some rest on test sets of 27-35 sites. Its
coverage explanation holds for XGBoost only: for the precipitation regression, rho with range
coverage is 0.18. Even for XGBoost it weakens in the incl_missing variant (rho -0.58). Its broader message,
that uneven sampling limits machine-learning Rs estimates, is already in print (Jiang 2025; Cao
2026), so its novelty rests on the design. A2, by contrast, has no precedent found in soil
respiration and is reusable by every group that maps Rs; its precedents are in other fields. If
hand checks of the Jian et al. 2018 and Bond-Lamberty & Thomson 2010 full texts confirm that neither
estimates a replicate-based ceiling, leading with A2 and using A1 as its application is a
defensible alternative.
