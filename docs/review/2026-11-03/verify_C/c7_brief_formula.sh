#!/bin/bash
# Check 7: does the brief (docs/handoff/PROMPT_mshi_v3.md) contain the "equal-study-weight" site-mean formula that the
# code, the committed result and DECISIONS.md D-P2-9 attribute to it?
R=/home/user/MSHI
echo "--- brief, Phase 2 item 3 (the whole text on the noise ceiling):"
grep -n "Noise ceiling" $R/docs/handoff/PROMPT_mshi_v3.md
echo "--- any formula / J_i / 'site mean' / 'equal' in the brief and the handoff bundle docs:"
grep -n -i "J_i\|/ *J\b\|s2_study\|study weight\|equal.*weight\|site mean\|site-mean" $R/docs/handoff/PROMPT_mshi_v3.md $R/docs/handoff/README.md $R/docs/handoff/prep_log.md $R/docs/handoff/ANALYSIS_PLAN_LOCKED.md || echo "(no match)"
echo "--- where the attribution 'the brief's formula' / 'brief's equal-study-weight formula' appears:"
grep -rn "brief's formula\|brief's equal-study-weight" $R/mshi $R/tests $R/docs/DECISIONS.md $R/results/noise_ceiling.json
echo "--- DECISIONS.md D-P2-9 (line-wrapped, so grep the two halves):"
grep -n "the brief.s$\|equal-study-weight formula" $R/docs/DECISIONS.md
