"""(a) tie-break chaining in clean_test.py L57-60 vs the plan rule; (b) fold partitions depend on each candidate's rows."""
import json
import numpy as np, pandas as pd
from sklearn.metrics import adjusted_rand_score
def code_rule(sel):                      # verbatim logic of clean_test.py L57-60
    sel = sorted(sel, key=lambda r: -r["cv_r2"]); best = sel[0]
    for r in sel[1:]:
        if best["cv_r2"] - r["cv_r2"] <= 0.01 and r["n_pred"] < best["n_pred"]: best = r
    return best
def plan_rule(sel):                      # plan L39: within 0.01 of the TOP, fewest predictors (ties -> higher CV R2)
    top = max(r["cv_r2"] for r in sel); ok = [r for r in sel if top - r["cv_r2"] <= 0.01]
    return sorted(ok, key=lambda r: (r["n_pred"], -r["cv_r2"]))[0]
toy = [dict(name="ALL-RF", cv_r2=0.150, n_pred=20), dict(name="C8+MODIS-RF", cv_r2=0.141, n_pred=12),
       dict(name="C8-RF", cv_r2=0.132, n_pred=8), dict(name="OLS-TP", cv_r2=0.123, n_pred=2)]
print("toy: code ->", code_rule(toy)["name"], "| plan ->", plan_rule(toy)["name"])
for f in ["clean_test_europe.json", "clean_test_selection_only.json", "clean_test_europe_repo_sensitivity.json"]:
    sel = json.load(open("/home/user/MSHI/docs/handoff/results/" + f))["selection_table"]
    c, p = code_rule(sel), plan_rule(sel); s = sorted(sel, key=lambda r: -r["cv_r2"])
    print(f, "code:", c["set"], c["learner"], "| plan:", p["set"], p["learner"], "| margin top-2nd %.4f" % (s[0]["cv_r2"] - s[1]["cv_r2"]))
# (b) partitions
A = pd.read_parquet("out/asia_384.parquet")
def folds(df, seed, deg=5.0, k=5):       # verbatim logic of clean_test.py L36-40
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); rng = np.random.default_rng(seed); rng.shuffle(u)
    for vb in np.array_split(u, k):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]
def labels(df, seed):
    lab = np.empty(len(df), int)
    for k, (tr, va) in enumerate(folds(df, seed)): lab[va] = k
    return pd.Series(lab, index=df.site_id.values)
blk = (np.floor(A.lon / 5).astype(int).astype(str) + "_" + np.floor(A.lat / 5).astype(int).astype(str))
cnt = blk.map(blk.value_counts())
full = labels(A, 42)
print("fold sizes seed42:", np.bincount(full.values).tolist(), "| seeds 42-44 sizes:", [np.bincount(labels(A, s).values).tolist() for s in (42, 43, 44)])
i_single = np.where(cnt.values == 1)[0][0]; i_shared = np.where(cnt.values > 5)[0][0]
for nm, i in [("singleton", i_single), ("shared", i_shared)]:
    sub = A.drop(index=A.index[i]).reset_index(drop=True); l2 = labels(sub, 42)
    print("drop one %s-block site -> ARI vs full partition on remaining sites: %.3f" % (nm, adjusted_rand_score(full.loc[l2.index].values, l2.values)))
g = np.random.default_rng(0)
for k in (2, 4, 5):
    ch = 0
    for _ in range(2000):
        drop = g.choice(len(A), k, replace=False); ch += np.any(cnt.values[drop] == 1)
    print("random drop of %d sites: P(partition changes) = %.3f" % (k, ch / 2000))
