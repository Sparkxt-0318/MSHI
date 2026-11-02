import sys, json, warnings
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/code")
from v_common import load
warnings.filterwarnings("ignore")

def varcomp_anova(df):  # identical to exp_noise_ceiling.varcomp
    g = df.groupby("site").log_rs; n = g.size(); k = len(n); N = n.sum()
    m = g.mean(); grand = df.log_rs.mean()
    ssb = (n * (m - grand) ** 2).sum(); ssw = ((df.log_rs - df.site.map(m)) ** 2).sum()
    msb, msw = ssb / (k - 1), ssw / (N - k); n0 = (N - (n ** 2).sum() / N) / (k - 1)
    return max((msb - msw) / n0, 0), msw

def reml3(df):
    md = smf.mixedlm("log_rs ~ 1", df, groups=df["site"], re_formula="1",
                     vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
    return float(md.cov_re.iloc[0, 0]), float(md.vcomp[0]), float(md.scale), md.converged

def reml1(df):
    md = smf.mixedlm("log_rs ~ 1", df, groups=df["site"]).fit(reml=True, method="lbfgs")
    return float(md.cov_re.iloc[0, 0]), float(md.scale)

r = load("qc")
r["study"] = r.site.astype(str) + "_" + r.study_id.astype(str)
n_i = r.groupby("site").size()
cont_site = r.groupby("site").continent.agg(lambda x: x.mode().iat[0])
# sum_j (m_ij/n_i)^2 for each site
comp = r.groupby(["site", "study"]).size().rename("m").reset_index()
comp["w2"] = (comp.m / comp.site.map(n_i)) ** 2
H = comp.groupby("site").w2.sum()
multi = r[r.site.map(n_i) >= 2]
print("sites", len(n_i), "multi-record sites", multi.site.nunique(), "records in multi", len(multi), "singletons", int((n_i == 1).sum()))
out = {}
for name, sel_multi, sel_sites in [("pooled", multi, n_i.index),
                                   ("Asia", multi[multi.site.map(cont_site) == "Asia"], cont_site.index[cont_site == "Asia"]),
                                   ("Europe", multi[multi.site.map(cont_site) == "Europe"], cont_site.index[cont_site == "Europe"]),
                                   ("North America", multi[multi.site.map(cont_site) == "North America"], cont_site.index[cont_site == "North America"])]:
    s2b, s2w = varcomp_anova(sel_multi)
    e1 = s2b / (s2b + (s2w / n_i.loc[sel_sites]).mean())
    ss, sst, sr, conv = reml3(sel_multi)
    noise = sst * H.loc[sel_sites] + sr / n_i.loc[sel_sites]
    c3 = ss / (ss + noise.mean())
    # "same-study" variant: study effect treated as signal (only meaningful for a same-study new record)
    o1b, o1w = reml1(sel_multi)
    out[name] = dict(n_sites=int(len(sel_sites)), n_multi_sites=int(sel_multi.site.nunique()),
                     anova_s2b=round(s2b, 4), anova_s2w=round(s2w, 4), E1_style_site_mean_ceiling=round(e1, 3),
                     reml3_site=round(ss, 4), reml3_study=round(sst, 4), reml3_rec=round(sr, 4), converged=bool(conv),
                     ceiling_3lvl_site_mean=round(c3, 3), mean_noise_E1=round(float((s2w / n_i.loc[sel_sites]).mean()), 4),
                     mean_noise_3lvl=round(float(noise.mean()), 4),
                     icc_anova=round(s2b / (s2b + s2w), 3), icc_reml1=round(o1b / (o1b + o1w), 3), icc_reml3_indep=round(ss / (ss + sst + sr), 3))
    print(name, out[name])
# singleton variance check
sing = n_i.index[n_i == 1]
ys = r[r.site.isin(sing)].set_index("site").log_rs
print("singletons:", len(sing), "var log_rs (ddof=1):", round(float(ys.var()), 4))
for c in ["Asia", "Europe", "North America"]:
    yy = ys[ys.index.map(cont_site) == c]
    print("  ", c, len(yy), round(float(yy.var()), 4))
p = out["pooled"]
print("implied single-record variance: E1", round(p["anova_s2b"] + p["anova_s2w"], 4), " 3-level", round(p["reml3_site"] + p["reml3_study"] + p["reml3_rec"], 4))
na = out["North America"]
print("NA implied: E1", round(na["anova_s2b"] + na["anova_s2w"], 4), " 3-level", round(na["reml3_site"] + na["reml3_study"] + na["reml3_rec"], 4))
# example from the finding: 10 records from one study
print("10 recs one study: 3-level noise", round(p["reml3_study"] + p["reml3_rec"] / 10, 4), " E1 noise", round(p["anova_s2w"] / 10, 4))
json.dump(out, open("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/out/v_ceiling.json", "w"), indent=1)
