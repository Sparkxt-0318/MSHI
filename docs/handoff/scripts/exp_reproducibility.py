"""N3 — Reproducibility of annual Rs: do independent studies at the same site agree?
For SRDB records merged into 5-km sites (v3 coordinate check + QC), compare pairs of records at the same site:
  same study (Study_number) vs different studies; split by same vs different year, and same vs different
  measurement method. Statistic: half squared difference of log Rs (= semivariance; sqrt ~ typical log SD).
Also a 3-level variance decomposition: site / study-within-site / record-within-study (REML mixed model),
and the 'reproducibility ceiling': share of variance a perfect site-level model could explain for a record
from an INDEPENDENT study = s2_site / total.
"""
import json, sys
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
import statsmodels.formula.api as smf

REC, SRDB, OUT = sys.argv[1:4]
r = pd.read_parquet(REC)
r = r[(r.src == "srdb") & ~r.f_offland & ~r.f_coord].copy()
s = pd.read_csv(SRDB, low_memory=False)
r["row"] = r.rec_id.str.replace("srdb_", "").astype(int)
for c in ["Study_number", "Site_ID", "Author", "Study_midyear", "Meas_method", "Partition_method", "Ecosystem_type"]:
    r[c] = s.loc[r.row, c].values
R = {}
for tag, rr in [("qc", r[~(r.f_method | r.f_quality | r.f_coverage | r.f_ecosys | r.f_dup)]), ("repo", r)]:
    rr = rr.reset_index(drop=True)
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    rr["site"] = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr),) * 2), directed=False)[1]
    pairs = {"same_study": [], "diff_study": [], "diff_study_same_year": [], "diff_study_same_method": [],
             "diff_study_same_year_same_method_same_ecosystem": [], "same_study_diff_year": [], "same_study_same_year": []}
    n_sites_multi_study = 0
    for _, g in rr.groupby("site"):
        if len(g) < 2: continue
        if g.Study_number.nunique() >= 2: n_sites_multi_study += 1
        v = g[["log_rs", "Study_number", "Study_midyear", "Meas_method", "Ecosystem_type"]].values
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                h = 0.5 * (v[i, 0] - v[j, 0]) ** 2
                if v[i, 1] == v[j, 1]:
                    pairs["same_study"].append(h)
                    (pairs["same_study_same_year"] if v[i, 2] == v[j, 2] else pairs["same_study_diff_year"]).append(h)
                else:
                    pairs["diff_study"].append(h)
                    if v[i, 2] == v[j, 2]: pairs["diff_study_same_year"].append(h)
                    if v[i, 3] == v[j, 3]: pairs["diff_study_same_method"].append(h)
                    if v[i, 2] == v[j, 2] and v[i, 3] == v[j, 3] and v[i, 4] == v[j, 4]:
                        pairs["diff_study_same_year_same_method_same_ecosystem"].append(h)
    R[tag] = {"sites_with_2plus_studies": n_sites_multi_study}
    for k, v in pairs.items():
        v = np.array(v)
        if len(v):
            rng = np.random.default_rng(0)
            bs = [np.mean(rng.choice(v, len(v))) for _ in range(1000)]
            R[tag][k] = dict(n_pairs=int(len(v)), semivar=round(float(v.mean()), 4), ci=[round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)],
                             typical_pct_diff=round(float(100 * (np.exp(np.sqrt(2 * v.mean())) - 1)), 1))
    # variance components (sites with >=2 records), REML: site + study-within-site random intercepts
    multi = rr[rr.groupby("site").log_rs.transform("size") >= 2].copy()
    multi["study"] = multi.site.astype(str) + "_" + multi.Study_number.astype(str)
    try:
        md = smf.mixedlm("log_rs ~ 1", multi, groups=multi["site"], re_formula="1", vc_formula={"study": "0 + C(study)"}).fit(reml=True, method="lbfgs")
        s2_site = float(md.cov_re.iloc[0, 0]); s2_study = float(md.vcomp[0]); s2_res = float(md.scale)
        tot = s2_site + s2_study + s2_res
        R[tag]["variance_components"] = dict(site=round(s2_site, 4), study_within_site=round(s2_study, 4), record=round(s2_res, 4),
                                             share_site=round(s2_site / tot, 3), share_study=round(s2_study / tot, 3), share_record=round(s2_res / tot, 3),
                                             ceiling_independent_study=round(s2_site / tot, 3),
                                             ceiling_same_study=round((s2_site + s2_study) / tot, 3))
    except Exception as e:
        R[tag]["variance_components"] = f"failed: {e}"
    R[tag]["total_var_logrs_sites"] = round(float(rr.groupby("site").log_rs.mean().var()), 4)
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps(R, indent=1))
