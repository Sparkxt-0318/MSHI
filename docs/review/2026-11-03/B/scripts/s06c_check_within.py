"""Known-answer check of the synthetic within_continent result: OLS-TP within-continent r2 should be close to the
oracle 1 - sigma^2/var(y) (any CV scheme; the model is correctly specified and noise is i.i.d.), and the transfer
penalty vs a pairwise training continent A close to (delta_A - delta_B)^2 / var(y_B) (+ estimation error)."""
import sys, json
sys.path.insert(0, "/home/user/MSHI")
from pathlib import Path
import numpy as np, pandas as pd
OUT = Path(sys.argv[1])
DELTA = {"Asia": 0.0, "Europe": 0.35, "North America": -0.25, "South America": 0.15, "Africa": -0.15, "Oceania": 0.05}
SIG = 0.25
W = json.loads((OUT / "out/results/within_continent.json").read_text())
truth = pd.read_parquet(OUT / "truth.parquet")
print("continents:", list(W["continents"]), "skipped:", [(s["continent"], s["n"]) for s in W["skipped"]])
for c, e in W["continents"].items():
    y = truth.loc[truth.continent_geo == c, "log_rs"].to_numpy()
    v = y.var()
    o = 1 - SIG ** 2 / v
    print(f"\n== {c} n={e['n']} var={v:.3f} oracle within r2={o:.3f}")
    print("   splits:", {k: (s["n_folds"], s["test_sizes"], round(s["W_km"], 1)) for k, s in e["splits"].items()})
    print("   knndm:", {k: e["knndm"]["diagnostics"].get(k) for k in ("q", "random_cv", "W", "W_random", "fold_sizes")})
    for learner, L in e["learners"].items():
        b = L.get("blocks", {}).get("seed_mean", {})
        k = L.get("knndm", {})
        print(f"   {learner:6s} blocks r2={b.get('r2', float('nan')):.3f} {np.round(b.get('ci', {}).get('r2', [np.nan, np.nan]), 3).tolist()} "
              f"knndm r2={k.get('r2', float('nan')):.3f} skill_blocks={b.get('skill_vs_train_mean', float('nan')):.3f}")
        if learner == "OLS-TP":
            for label, pen in L["penalty_r2"].items():
                exp = ((DELTA[label] - DELTA[c]) ** 2 / v) if label in DELTA else None
                pb = pen.get("blocks", {})
                print(f"      penalty vs {label:14s} blocks={pb.get('point', float('nan')):.3f} CI={np.round(pb.get('ci', [np.nan, np.nan]), 3).tolist()} "
                      f"knndm={pen.get('knndm', {}).get('point', float('nan')):.3f}" + (f"  expected~{exp:.3f}" if exp is not None else ""))
