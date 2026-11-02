"""Selection rule: code (clean_test.py L57-60) vs plan text ('within 0.01 of the highest and fewer predictors')."""
import json, sys
def code_rule(sel):                      # verbatim logic of clean_test.py L57-60
    sel = sorted(sel, key=lambda r: -r["cv_r2"]); best = sel[0]
    for r in sel[1:]:
        if best["cv_r2"] - r["cv_r2"] <= 0.01 and r["n_pred"] < best["n_pred"]: best = r
    return best["name"]
def plan_rule(sel):                      # reference fixed at the top score; simplest within 0.01, ties -> higher CV R2
    top = max(r["cv_r2"] for r in sel)
    ok = [r for r in sel if top - r["cv_r2"] <= 0.01]
    return min(ok, key=lambda r: (r["n_pred"], -r["cv_r2"]))["name"]
cases = {
 "chain": [dict(name="ALL-RF", n_pred=20, cv_r2=0.150), dict(name="C8+MODIS-RF", n_pred=12, cv_r2=0.141),
           dict(name="C8-RF", n_pred=8, cv_r2=0.132), dict(name="OLS-TP", n_pred=2, cv_r2=0.123)],
 "actual_run": json.load(open(sys.argv[1]))["selection_table"],
 "actual_repo_run": json.load(open(sys.argv[2]))["selection_table"],
}
for k in ("actual_run", "actual_repo_run"):
    for r in cases[k]: r["name"] = f'{r["set"]}-{r["learner"]}'
for k, v in cases.items():
    print(k, "| code picks:", code_rule(v), "| plan picks:", plan_rule(v))
