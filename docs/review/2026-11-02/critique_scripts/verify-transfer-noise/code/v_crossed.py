import sys, warnings
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/code")
from v_common import load
warnings.filterwarnings("ignore")
r = load("qc", srdb_only=True)                       # N3 data: SRDB-only, coord check + QC, 5-km sites
print("QC SRDB records:", len(r), " unique Study_number:", r.S_Study_number.nunique())
ns = r.groupby("S_Study_number").site.nunique()
print("Study_numbers spanning >=2 sites (all QC SRDB records):", int((ns >= 2).sum()), "of", len(ns))
multi = r[r.groupby("site").log_rs.transform("size") >= 2].copy()
multi["study"] = multi.site.astype(str) + "_" + multi.S_Study_number.astype(str)
ns2 = multi.groupby("S_Study_number").site.nunique()
print("multi-record-site data:", len(multi), "records,", multi.site.nunique(), "sites,", len(ns2), "Study_numbers;", int((ns2 >= 2).sum()), "span >=2 sites")
# nested (exactly as exp_reproducibility.py:60) with several optimizers
for meth in ["lbfgs", "nm", "bfgs", "powell"]:
    try:
        md = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1", vc_formula={"study": "0 + C(study)"}).fit(reml=True, method=meth)
        a, b, c = float(md.cov_re.iloc[0, 0]), float(md.vcomp[0]), float(md.scale); t = a + b + c
        print(f"nested [{meth:6s}] site {a:.4f} study {b:.4f} rec {c:.4f} shares {a/t:.3f}/{b/t:.3f}/{c/t:.3f} converged={md.converged} llf={md.llf:.3f}")
    except Exception as e:
        print("nested", meth, "failed", e)
# crossed: independent blocks = connected components of the site–Study_number bipartite graph
sites = multi.site.astype("category").cat.codes.values; stud = multi.S_Study_number.astype("category").cat.codes.values
ns_, nt_ = sites.max() + 1, stud.max() + 1
A = coo_matrix((np.ones(len(multi)), (sites, ns_ + stud)), shape=(ns_ + nt_,) * 2)
nb, lab = connected_components(A, directed=False)
multi["block"] = lab[sites]
print("independent blocks:", multi.block.nunique())
md = smf.mixedlm("log_rs ~ 1", multi, groups=multi["block"], re_formula="0",
                 vc_formula={"site": "0 + C(site)", "stud": "0 + C(S_Study_number)"}).fit(reml=True, method="lbfgs")
names = list(md.model.exog_vc.names); vc = dict(zip(names, md.vcomp)); c = float(md.scale)
a, b = float(vc["site"]), float(vc["stud"]); t = a + b + c
print(f"crossed: site {a:.4f} study {b:.4f} rec {c:.4f} shares {a/t:.3f}/{b/t:.3f}/{c/t:.3f} converged={md.converged}")
