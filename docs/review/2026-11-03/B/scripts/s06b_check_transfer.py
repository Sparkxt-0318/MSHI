"""Known-answer check of the synthetic transfer_matrix result: OLS-TP pairwise bias should be delta_A - delta_B; r2 and
skill vs their oracle values (true climate part + training continent offset); CI coverage of the oracle."""
import sys, json
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd
OUT = Path(sys.argv[1])
DELTA = {"Asia": 0.0, "Europe": 0.35, "North America": -0.25, "South America": 0.15, "Africa": -0.15, "Oceania": 0.05}
R = json.loads((OUT / "out/results/transfer_matrix.json").read_text())
truth = pd.read_parquet(OUT / "out/data/interim/features_analysis_qc.parquet").set_index("site_id"); truth["truth_clim"] = 4.5 + 0.07 * truth.bio01 + 0.35 * np.log(truth.bio12)
tp = pd.read_parquet(OUT / "out/data/interim/transfer_predictions_qc.parquet")
print("sites:", R["sites"]["by_continent"], "skipped:", [(s["train"], s.get("n_train"), s["reason"][:40]) for s in R["skipped"]])
rows = R["main"] + R["supplementary"]
cover = {"bias_log": [0, 0], "r2": [0, 0]}
print(f"{'table':8s} {'train':14s} {'test':14s} {'learner':6s} {'bias':>7s} {'exp':>6s} {'r2':>6s} {'oracle':>6s} {'skill':>6s} {'n':>4s} r2 CI")
for r in rows:
    g = tp[(tp.table == r["table"]) & (tp.train == r["train"]) & (tp.test == r["test"]) & (tp.learner == r["learner"])]
    t = truth.loc[g.site_id]
    y = g.obs_log.to_numpy()
    if r["table"] == "pairwise":
        dtr = DELTA[r["train"]]
    else:
        tr = truth[truth.continent_geo.isin(r["train_continents"])]
        dtr = tr.continent_geo.map(DELTA).mean()       # pooled fit absorbs the n-weighted mean offset (approx.)
    oracle_pred = t.truth_clim.to_numpy() + dtr
    o_r2 = 1 - np.sum((oracle_pred - y) ** 2) / np.sum((y - y.mean()) ** 2)
    exp_bias = dtr - DELTA[r["test"]]
    if r["learner"] == "OLS-TP":
        lo, hi = r["ci"]["bias_log"]; cover["bias_log"][0] += lo <= exp_bias <= hi; cover["bias_log"][1] += 1
        lo, hi = r["ci"]["r2"]; cover["r2"][0] += lo <= o_r2 <= hi; cover["r2"][1] += 1
        print(f"{r['table']:8s} {r['train']:14s} {r['test']:14s} {r['learner']:6s} {r['bias_log']:7.3f} {exp_bias:6.3f} {r['r2']:6.3f} {o_r2:6.3f} "
              f"{r['skill_vs_train_mean']:6.3f} {r['n_test']:4d} [{r['ci']['r2'][0]:.3f}, {r['ci']['r2'][1]:.3f}]")
print("OLS-TP: oracle inside 95% CI (bias, r2):", cover)
