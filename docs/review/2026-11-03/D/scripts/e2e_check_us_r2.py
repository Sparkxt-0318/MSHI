"""Area D end-to-end, step 4: checks on the sandbox's us_r2 result and its seams with the other Phase-2 results.

- 48 rows (2 variants x 2 targets x 2 training regions x 2 learners x 3 test regions), 24 target effects, labels
- exploratory flags; inputs/outputs recorded; figure files exist
- seed spread: seeds as configured; seed-0 r2 inside [min, max]
- us_r2 (qc, site_mean, Asia -> North America) rows equal transfer_matrix's pairwise Asia -> North America rows
- n_test of each test region = the composition count minus excluded overlaps
- run log: every Phase-2 stage record carries exploratory = true
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config
from mshi.io import result_staleness

cfg = load_config(Path(sys.argv[1]))
res_dir = cfg.path("results")
R = json.loads((res_dir / "us_r2.json").read_text())
print("staleness us_r2:", result_staleness(cfg, R))
print("exploratory:", R["exploratory"], "| inputs:", sorted(R["_inputs"]), "| outputs:", sorted(R["_outputs"]))
rows, eff = R["rows"], R["target_effect"]
print("rows:", len(rows), "target effects:", len(eff), "skipped:", R["skipped"])
keys = {(r["variant"], r["target"], r["train"], r["learner"], r["test"]) for r in rows}
print("distinct row keys:", len(keys))
for v in R["variants"]:
    V = R["variants"][v]
    print(f"[{v}] sites:", V["sites"], "| single_record:", V["single_record"])
    for name, e in V["regions"].items():
        print(f"[{v}]   {name}: n={e['n']} {e.get('by_country', e['by_continent_geo'])}")
    print(f"[{v}]   overlaps:", [(o["train"], o["test"], o["n"]) for o in V["overlaps"] if o["n"]])
spread_ok = all(r["seed_spread"]["r2"]["min"] - 1e-12 <= r["r2"] <= r["seed_spread"]["r2"]["max"] + 1e-12
                for r in rows if r["learner"] == "XGB")
print("seed spread seeds:", {tuple(r["seed_spread"]["seeds"]) for r in rows if r["learner"] == "XGB"},
      "| seed-0 r2 within [min,max]:", spread_ok)
print("ci contains point (r2):", sum(r["ci"]["r2"][0] <= r["r2"] <= r["ci"]["r2"][1] for r in rows), "of", len(rows))
for r in rows:
    if r["variant"] == "qc" and r["target"] == "site_mean":
        print(f"  qc site_mean {r['train']:9s} {r['learner']:6s} -> {r['test']:42s} n={r['n_train']}/{r['n_test']} "
              f"r2={r['r2']:.3f} [{r['ci']['r2'][0]:.3f},{r['ci']['r2'][1]:.3f}] rmse={r['rmse_log']:.3f} "
              f"sd={r['sd_log']:.3f} seeds r2 {r.get('seed_spread', {}).get('r2')}")
M = json.loads((res_dir / "transfer_matrix.json").read_text())
for learner in ("OLS-TP", "XGB"):
    t = [x for x in M["main"] + M["supplementary"] if (x["table"], x["train"], x["test"], x["learner"]) ==
         ("pairwise", "Asia", "North America", learner)]
    u = [x for x in rows if (x["variant"], x["target"], x["train"], x["test"], x["learner"]) ==
         ("qc", "site_mean", "Asia", "North America", learner)]
    if t and u:
        t, u = t[0], u[0]
        same = all(abs(u[k] - t[k]) < 1e-12 for k in ("r2", "skill_vs_train_mean", "bias_log", "null_bias_log",
                                                     "rmse_log", "rmse_rs"))
        same_ci = all(abs(a - b) < 1e-12 for k in ("r2", "rmse_log") for a, b in zip(u["ci"][k], t["ci"][k]))
        print(f"seam us_r2 vs transfer_matrix ({learner}): n {u['n_train']}/{u['n_test']} vs {t['n_train']}/{t['n_test']}; "
              f"metrics equal: {same}; CIs equal: {same_ci}")
log = [json.loads(x) for x in (res_dir / "run_log.jsonl").read_text().splitlines()]
p2 = ["noise_ceiling", "europe_geo_sensitivity", "features_analysis", "transfer_matrix", "within_continent",
      "aoa_sensitivity", "us_r2"]
for s in p2:
    recs = [x for x in log if x["stage"] == s]
    print(f"run log {s}: {len(recs)} records, exploratory flags {sorted({str(x.get('exploratory')) for x in recs})}, "
          f"statuses {[x['status'][:40] for x in recs]}")
for name in ("noise_ceiling", "transfer_matrix", "within_continent", "aoa_sensitivity", "us_r2", "features_analysis"):
    p = res_dir / f"{name}.json"
    if p.exists():
        o = json.loads(p.read_text())
        print(f"{name}: exploratory={o.get('exploratory')} inputs={sorted(o.get('_inputs', {}))} "
              f"outputs={sorted(o.get('_outputs', {}))} stale={result_staleness(cfg, o)}")
