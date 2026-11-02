"""Replicate N2b (exp_forest_bias.py) on the verifier's proxy: the handoff totals() is copied verbatim (statsmodels)."""
import sys, json, numpy as np, pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites, cells, V
NB = int(sys.argv[1]) if len(sys.argv) > 1 else 500
out = {}
for tag, sfill, cfill in [("sites577_cells_atlas_only", False, False), ("sites577_cells_filled", False, True), ("sites581_cells_filled", True, True)]:
    d = sites(fill=sfill); g = cells(fill=cfill)
    def totals(s):  # verbatim from exp_forest_bias.py L58-69
        out = {}
        mA = smf.ols("log_rs ~ bio01 + lnP + C(continent)", data=s).fit()
        mB = smf.ols("log_rs ~ bio01 + lnP + pixel_forest + C(continent)", data=s).fit()
        mC = smf.ols("log_rs ~ bio01 + lnP + plot_forest + C(continent)", data=s).fit()
        sm = {k: np.mean(np.exp(m.resid)) for k, m in [("A", mA), ("B", mB), ("C", mC)]}
        A = np.exp(mA.predict(g)) * sm["A"]
        B = g.f * np.exp(mB.predict(g.assign(pixel_forest=1))) * sm["B"] + (1 - g.f) * np.exp(mB.predict(g.assign(pixel_forest=0))) * sm["B"]
        C = g.f * np.exp(mC.predict(g.assign(plot_forest=1))) * sm["C"] + (1 - g.f) * np.exp(mC.predict(g.assign(plot_forest=0))) * sm["C"]
        for k, v in [("A", A), ("B", B), ("C", C)]:
            out[k] = float((v * g.veg_area_m2).sum() / 1e15)
        return out, mB.params.pixel_forest, mC.params.plot_forest
    rng = np.random.default_rng(0)
    base, b_pix, b_plot = totals(d)
    boots = []
    for _ in range(NB):
        s = d.iloc[rng.integers(0, len(d), len(d))]
        t, bp, bq = totals(s); boots.append((t["A"] / t["C"] - 1, t["B"] / t["C"] - 1, bp, bq))
    boots = np.array(boots)
    q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
    out[tag] = dict(n_sites=int(len(d)), plot_forest_share=round(float(d.plot_forest.mean()), 3), pixel_forest_share=round(float(d.pixel_forest.mean()), 3),
         landscape_forest_share_area_weighted=round(float(np.average(g.f, weights=g.veg_area_m2)), 3),
         coef_plot_forest=round(float(b_plot), 3), coef_plot_forest_ci=q(boots[:, 3]),
         coef_pixel_forest=round(float(b_pix), 3), coef_pixel_forest_ci=q(boots[:, 2]),
         totals_PgC={k: round(v, 2) for k, v in base.items()},
         inflation_A_climate_only=round(base["A"] / base["C"] - 1, 3), inflation_A_ci=q(boots[:, 0]),
         inflation_B_pixel_landcover=round(base["B"] / base["C"] - 1, 3), inflation_B_ci=q(boots[:, 1]),
         footprint_cells=int(len(g)))
    print(tag, json.dumps(out[tag]))
json.dump(out, open(f"{V}/out/n2b_replicate.json", "w"), indent=1)
