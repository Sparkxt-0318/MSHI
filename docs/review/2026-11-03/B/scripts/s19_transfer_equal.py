"""within_continent.json note: 'transfer metrics recomputed from transfer_matrix's predictions with the same bootstrap;
they equal the rows of results/transfer_matrix.json' -- checked for every learner, continent and training label."""
import sys, json
from pathlib import Path
OUT = Path(sys.argv[1])
TM = json.loads((OUT / "out/results/transfer_matrix.json").read_text())
WC = json.loads((OUT / "out/results/within_continent.json").read_text())
rows = {(r["table"], r["train"], r["test"], r["learner"]): r for r in TM["main"] + TM["supplementary"]}
n = bad = 0
for c, e in WC["continents"].items():
    for learner, L in e["learners"].items():
        for label, m in L["transfer"].items():
            r = rows[("loco" if label == "LOCO" else "pairwise", label, c, learner)]
            n += 1
            for k in ("r2", "skill_vs_train_mean", "bias_log", "null_bias_log", "rmse_log", "rmse_rs"):
                if m[k] != r[k] or m["ci"][k] != r["ci"][k]:
                    bad += 1
                    print("differs:", c, learner, label, k, m[k], r[k])
print(f"{n} (continent, learner, training label) entries compared; {bad} metric differences")
