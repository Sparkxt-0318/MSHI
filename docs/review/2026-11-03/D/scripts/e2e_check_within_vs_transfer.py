"""Seam: within_continent's transfer metrics (recomputed from transfer_matrix's predictions table) must equal the
rows of transfer_matrix.json (same sites, predictions and bootstrap replicates), as within_continent's notes claim."""
import json, sys
from pathlib import Path
snap = Path(sys.argv[1])
W = json.loads((snap / "results/within_continent.json").read_text())
M = json.loads((snap / "results/transfer_matrix.json").read_text())
rows = {(r["train"], r["test"], r["learner"]): r for r in M["main"] + M["supplementary"]}
n = bad = 0
for c, e in W["continents"].items():
    for learner, L in e["learners"].items():
        for label, t in L["transfer"].items():
            r = rows[(label, c, learner)]
            n += 1
            diffs = {k: abs(t[k] - r[k]) for k in ("r2", "skill_vs_train_mean", "bias_log", "null_bias_log", "rmse_log", "rmse_rs")}
            cid = max(abs(a - b) for k in ("r2", "rmse_log") for a, b in zip(t["ci"][k], r["ci"][k]))
            if max(diffs.values()) > 1e-12 or cid > 1e-12:
                bad += 1
                print("DIFF", c, learner, label, diffs, cid)
print(f"within transfer entries checked: {n}; differing from transfer_matrix rows: {bad}")
