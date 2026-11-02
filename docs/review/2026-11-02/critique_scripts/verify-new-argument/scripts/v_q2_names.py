"""Finding 08: what parameter names does the N2 Q2 formula produce, and does the 'plot' filter (exp_plot_pixel.py L52-53) match any?"""
import numpy as np, pandas as pd, statsmodels.formula.api as smf
rng = np.random.default_rng(0); n = 200
a = pd.DataFrame({"log_rs": rng.normal(6.5, .5, n), "bio01": rng.normal(10, 5, n), "lnP": rng.normal(7, .4, n),
                  "ptype": rng.choice(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"], n),
                  "continent": rng.choice(["Asia", "North America", "Europe"], n),
                  "pixel": rng.choice(["Agriculture", "Forest", "Grassland", "Other", "Savanna", "Shrubland"], n)})
m = smf.ols("log_rs ~ bio01 + lnP + C(ptype, Treatment('Forest')) + C(continent)", data=a).fit(cov_type="HC3")
print(list(m.params.index))
sel = {k.split("]")[0].split("T.")[-1]: 1 for k, v in m.params.items() if "plot" in k}
print("L52-53 filter result:", sel, "| any('plot' in k):", any("plot" in k for k in m.params.index), "| any('ptype' in k):", any("ptype" in k for k in m.params.index))
mp = smf.ols("log_rs ~ bio01 + lnP + C(pixel) + C(continent)", data=a).fit(cov_type="HC3")
print([k for k in mp.params.index if "pixel" in k], "-> reference level (absent):", sorted(set(a.pixel)) [0])
