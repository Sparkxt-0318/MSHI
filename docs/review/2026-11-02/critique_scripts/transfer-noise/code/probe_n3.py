import sys, warnings, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
import statsmodels.formula.api as smf
W=sys.argv[1]; SRDB=sys.argv[2]
r = pd.read_parquet(f"{W}/data/records_v3.parquet")
r = r[(r.src == "srdb") & ~r.f_offland & ~r.f_coord].copy()
s = pd.read_csv(SRDB, low_memory=False)
r["row"] = r.rec_id.str.replace("srdb_", "").astype(int)
for c in ["Study_number", "Study_midyear", "Meas_method", "Ecosystem_type"]:
    r[c+"_s"] = s.loc[r.row, c].values
r["Study_number"]=r["Study_number_s"]
rr = r[~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)].reset_index(drop=True)
X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
rr["site"] = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
multi = rr[rr.groupby("site").log_rs.transform("size") >= 2].copy()
multi["study"] = multi.site.astype(str) + "_" + multi.Study_number.astype(str)
print("multi records", len(multi), "sites", multi.site.nunique(), "studies", multi.study.nunique())
with warnings.catch_warnings(record=True) as wl:
    warnings.simplefilter("always")
    md = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1", vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
print("converged:", md.converged, "warnings:", [str(w.message)[:120] for w in wl])
print("site var", md.cov_re.iloc[0,0], "study var", md.vcomp, "resid", md.scale)
# alternative optimizer check
md2 = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1", vc_formula={"study": "0 + C(study)"}).fit(reml=True, method=["nm","bfgs"], maxiter=5000)
print("alt optimizer: site", md2.cov_re.iloc[0,0], "study", md2.vcomp, "resid", md2.scale, "conv", md2.converged)
# Structure: how many sites have >=2 studies; how many studies have >=2 records
st = multi.groupby("site").study.nunique()
print("sites with >=2 studies", (st>=2).sum(), "of", len(st))
ns = multi.groupby("study").size()
print("studies with >=2 records", (ns>=2).sum(), "of", len(ns))
# Is Study_number shared across sites? (nesting check)
print("Study_numbers spanning >1 site:", (multi.groupby("Study_number").site.nunique()>1).sum(), "of", multi.Study_number.nunique())
# one-way REML (site only) on same SRDB data, vs ANOVA estimator
m1 = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"]).fit(reml=True)
print("one-way REML site", m1.cov_re.iloc[0,0], "resid", m1.scale, "ICC", m1.cov_re.iloc[0,0]/(m1.cov_re.iloc[0,0]+m1.scale))
g = multi.groupby("site").log_rs; n = g.size(); k=len(n); N=n.sum(); mm=g.mean(); grand=multi.log_rs.mean()
ssb=(n*(mm-grand)**2).sum(); ssw=((multi.log_rs-multi.site.map(mm))**2).sum(); msb=ssb/(k-1); msw=ssw/(N-k); n0=(N-(n**2).sum()/N)/(k-1)
s2b=(msb-msw)/n0
print("ANOVA (srdb-only multi) s2b", s2b, "s2w", msw, "ICC", s2b/(s2b+msw))
# site-weighted within variance
sv = g.var(ddof=1)
print("record-weighted MSW", msw, "site-weighted mean within-site var", sv.mean(), "median", sv.median())
