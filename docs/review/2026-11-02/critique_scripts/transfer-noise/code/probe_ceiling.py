import sys, warnings, json, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
import statsmodels.formula.api as smf
warnings.filterwarnings("ignore")
W=sys.argv[1]; SRDB=sys.argv[2]
r = pd.read_parquet(f"{W}/data/records_v3.parquet")
r = r[~r.f_offland & ~r.f_coord].copy()
s = pd.read_csv(SRDB, low_memory=False)
isS = r.src.eq("srdb")
r["Study_number"] = pd.Series([None]*len(r), index=r.index, dtype=object)
r.loc[isS, "Study_number"] = s.loc[r.loc[isS,"rec_id"].str.replace("srdb_","").astype(int), "Study_number"].values
r.loc[~isS, "Study_number"] = ["cos_"+x for x in r.loc[~isS,"rec_id"]]   # each COSORE dataset its own study
QC = ~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)
def cluster(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    return connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
def anova(df):
    g = df.groupby("site").log_rs; n = g.size(); k = len(n); N = n.sum()
    m = g.mean(); grand = df.log_rs.mean()
    ssb = (n * (m - grand) ** 2).sum(); ssw = ((df.log_rs - df.site.map(m)) ** 2).sum()
    msb, msw = ssb / (k - 1), ssw / (N - k); n0 = (N - (n ** 2).sum() / N) / (k - 1)
    return max((msb - msw) / n0, 0), msw
out = {}
for tag, rr in [("qc", r[QC]), ("repo", r)]:
    rr = rr.reset_index(drop=True); rr["site"] = cluster(rr)
    # continent of a site = mode over records (as build_sites_v3)
    sc = rr.groupby("site").continent.agg(lambda x: x.mode().iat[0]); rr["sitecont"] = rr.site.map(sc)
    rr["study"] = rr.site.astype(str) + "_" + rr.Study_number.astype(str)
    res = {}
    for cont in ["ALL", "Asia", "Europe", "North America"]:
        sub = rr if cont == "ALL" else rr[rr.sitecont == cont]
        multi = sub[sub.groupby("site").log_rs.transform("size") >= 2]
        s2b, s2w = anova(multi)
        n_i = sub.groupby("site").size()
        ceil_e1 = s2b / (s2b + (s2w / n_i).mean())
        md = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1", vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
        a, b, c = float(md.cov_re.iloc[0, 0]), float(md.vcomp[0]), float(md.scale)
        # noise variance of each site's observed mean under the 3-level model: s2_study*sum_j (m_ij/n_i)^2 + s2_rec/n_i
        cnt = sub.groupby(["site", "study"]).size()
        ni = cnt.groupby(level=0).sum()
        noise3 = b * (cnt ** 2).groupby(level=0).sum() / ni ** 2 + c / ni
        ceil3 = a / (a + noise3.mean())
        m1 = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"]).fit(reml=True)
        res[cont] = dict(sites_all=int(len(n_i)), sites_multi=int(multi.site.nunique()),
                         anova_icc_single=round(s2b/(s2b+s2w),3), e1_style_site_mean_ceiling=round(ceil_e1,3),
                         reml1_icc=round(m1.cov_re.iloc[0,0]/(m1.cov_re.iloc[0,0]+m1.scale),3),
                         reml3=dict(site=round(a,4), study=round(b,4), record=round(c,4), conv=bool(md.converged)),
                         ceil_independent_study_single=round(a/(a+b+c),3), ceil_same_study_single=round((a+b)/(a+b+c),3),
                         site_mean_ceiling_3level=round(ceil3,3),
                         var_observed_site_means=round(float(sub.groupby("site").log_rs.mean().var()),4))
    out[tag] = res
print(json.dumps(out, indent=1))
json.dump(out, open(f"{W}/out/ceilings.json","w"), indent=1)
