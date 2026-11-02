import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/code")
from v_common import load
r = load("qc")
n_i = r.groupby("site").size(); cont = r.groupby("site").continent.agg(lambda x: x.mode().iat[0])
ym = r.groupby("site").log_rs.mean()
C = json.load(open("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/out/v_ceiling.json"))
for name, idx in [("pooled", ym.index), ("Asia", ym.index[cont == "Asia"]), ("Europe", ym.index[cont == "Europe"]), ("North America", ym.index[cont == "North America"])]:
    c = C[name]; vo = float(ym.loc[idx].var(ddof=0))
    print(f"{name:14s} observed var(site-mean target)={vo:.4f} | E1 implied={c['anova_s2b']+c['mean_noise_E1']:.4f}  3lvl implied={c['reml3_site']+c['mean_noise_3lvl']:.4f} "
          f"| 1-noise/var_obs: E1 {1-c['mean_noise_E1']/vo:.3f}  3lvl {1-c['mean_noise_3lvl']/vo:.3f}")
# ecosystem-type split of within-site pairs (QC, multi-record sites)
def pairs(df, key):
    out = {"same": [], "diff": []}; site_mix = 0
    for _, g in df.groupby("site"):
        if len(g) < 2: continue
        v = g[["log_rs", key]].values
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                if pd.isna(v[i, 1]) or pd.isna(v[j, 1]): continue
                out["same" if v[i, 1] == v[j, 1] else "diff"].append(0.5 * (v[i, 0] - v[j, 0]) ** 2)
    return out
for lab, df in [("all records (COSORE igbp as type)", r), ("SRDB records only", r[r.src == "srdb"])]:
    p = pairs(df, "Ecosystem_type"); ns, nd = len(p["same"]), len(p["diff"])
    print(f"{lab}: pairs same={ns} diff={nd} share_diff={nd/(ns+nd):.3f}  semivar same={np.mean(p['same']):.4f} diff={np.mean(p['diff']):.4f}")
fr = r.Ecosystem_type.astype(str).str.contains("forest", case=False)
has = r.Ecosystem_type.notna()
mix = r[has].assign(fr=fr[has]).groupby("site").fr.agg(lambda x: x.any() and (~x).any())
print("sites mixing forest and non-forest records (all records):", int(mix.sum()))
rs = r[(r.src == "srdb") & has]
mix2 = rs.assign(fr=rs.Ecosystem_type.eq("Forest")).groupby("site").fr.agg(lambda x: x.any() and (~x).any())
print("sites mixing (SRDB only, 'Forest' vs other):", int(mix2.sum()))
print(r.Ecosystem_type.value_counts(dropna=False).head(15).to_dict())
