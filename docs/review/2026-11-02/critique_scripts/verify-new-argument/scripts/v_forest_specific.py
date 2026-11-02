"""Finding 04 (last part): is the binary plot-forest effect forest-specific? Binary coefficient after removing classes."""
import sys, numpy as np, pandas as pd, statsmodels.formula.api as smf
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import sites
d = sites(fill=False)
print("pt counts in N2b proxy sample:", d.pt.value_counts().to_dict())
for lab, m in [("all (N2b spec)", np.ones(len(d), bool)), ("drop Shrub/Savanna/Desert", ~d.pt.isin(["Shrubland", "Savanna", "Desert"])),
               ("non-forest = Grassland only", d.pt.isin(["Forest", "Grassland"])), ("non-forest = Agriculture only", d.pt.isin(["Forest", "Agriculture"]))]:
    s = d[m]; r = smf.ols("log_rs ~ bio01 + lnP + plot_forest + C(continent)", data=s).fit(cov_type="HC3")
    print(f"{lab:32s} n={len(s)} plot_forest {r.params.plot_forest:.3f} [{r.conf_int().loc['plot_forest', 0]:.3f}, {r.conf_int().loc['plot_forest', 1]:.3f}]")
