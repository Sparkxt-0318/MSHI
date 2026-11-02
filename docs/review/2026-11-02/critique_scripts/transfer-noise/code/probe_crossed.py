import sys, warnings, time, numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
import statsmodels.formula.api as smf
warnings.filterwarnings("ignore")
W=sys.argv[1]; SRDB=sys.argv[2]
r = pd.read_parquet(f"{W}/data/records_v3.parquet")
r = r[(r.src == "srdb") & ~r.f_offland & ~r.f_coord].copy()
s = pd.read_csv(SRDB, low_memory=False)
r["row"] = r.rec_id.str.replace("srdb_", "").astype(int); r["Study_number"] = s.loc[r.row, "Study_number"].values
rr = r[~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)].reset_index(drop=True)
X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
rr["site"] = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
multi = rr[rr.groupby("site").log_rs.transform("size") >= 2].copy()
multi["study_raw"] = multi.Study_number.astype(int).astype(str)
# Studies spanning >1 site: do they link sites? Use connected components of the site-study bipartite graph as independent groups
sites = multi.site.unique(); studies = multi.study_raw.unique()
si = {k:i for i,k in enumerate(sites)}; ti = {k:i+len(sites) for i,k in enumerate(studies)}
e = multi[["site","study_raw"]].drop_duplicates()
A = coo_matrix((np.ones(len(e)), ([si[a] for a in e.site], [ti[b] for b in e.study_raw])), shape=(len(sites)+len(studies),)*2)
_, lab = connected_components(A, directed=False)
multi["grp"] = [lab[si[a]] for a in multi.site]
print("independent blocks (site-study components):", multi.grp.nunique(), "largest block records:", multi.groupby("grp").size().max())
t=time.time()
m = smf.mixedlm("log_rs ~ 1", multi, groups=multi["grp"], re_formula="0",
                vc_formula={"site": "0 + C(site)", "study": "0 + C(study_raw)"}).fit(reml=True, method="lbfgs")
names = m.model.exog_vc.names
print("crossed fit converged:", m.converged, "secs", round(time.time()-t,1))
vc = dict(zip(names, m.vcomp)); a, b, c = vc["site"], vc["study"], m.scale
print(f"crossed: site {a:.4f} study {b:.4f} record {c:.4f} -> share site {a/(a+b+c):.3f} study {b/(a+b+c):.3f} record {c/(a+b+c):.3f}")
print("nested (N3): site 0.2926 study 0.0704 record 0.0684 -> share 0.678 / 0.163 / 0.159")
