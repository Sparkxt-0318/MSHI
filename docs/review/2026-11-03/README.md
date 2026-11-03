# Phase-2 code review (2026-11-03)

The one review round of the Phase-2 code that the author allowed (docs/DECISIONS.md R-P2-1). Four reviewers
read the code at commit `ec43c6c`, each in its own area, and confirmed every finding by running code in scratch
sandboxes (the repository read-only). An independent adversarial verifier then re-ran every finding and tried to
refute it. The brief they all worked from is `contract.txt`.

- `findings.md`: the 17 findings with scenario, evidence, the reviewer's and the verifier's reasoning and fix, and
  what each reviewer checked and found correct. After verification: 1 high, 3 medium and 13 low (14 confirmed as
  reported, 3 in part).
- `A/`, `B/`, `C/`, `D/`: the reviewers' scripts, logs and small result files (areas: integration, provenance, the
  analysis site build and the docs; transfer matrix, within-continent benchmark and kNNDM; noise ceiling and AOA;
  US R² and an end-to-end run on stand-ins). `verify_A/` to `verify_D/`: the verifiers'. Sandboxes, copies of the
  repository and downloaded third-party sources are not included; paths in the logs are the scratch paths of the
  review machine.
- `fixcheck/`: checks of the fixes run afterwards against the review's own results (South America refits with and
  without the fallback optimisers; every bootstrap replicate of four continents against the review's independent
  REML maxima).

Fixes: DECISIONS.md D-P2-13 to D-P2-17 and the list after them. Every number in those entries comes from a script
here or from a test in `tests/`.
