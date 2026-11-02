"""Overlap between the locked-test Europe sites (235) and the ORIGINAL Asia-box training tables.
(1) exact: shared SRDB record ids; (2) spatial: haversine distance from each test site to the nearest training row."""
import sys, json
import numpy as np, pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
V3 = sys.argv[1]; P = sys.argv[2]; SRDB = sys.argv[3]
r = pd.read_parquet(V3 + "/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord]
def site_labels(rr):
    X = np.radians(rr[["lat", "lon"]].values); tree = BallTree(X, metric="haversine")
    nb = tree.query_radius(X, r=5.0 / 6371.0)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr), len(rr)))
    return connected_components(A, directed=False)[1]
out = {}
for tag, rr, adrop, edrop in [("qc", base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)], ["v3qc_00184","v3qc_00576","v3qc_00604"], ["v3qc_00559"]),
                              ("repo", base, [], [])]:
    rr = rr.reset_index(drop=True).copy(); rr["site_id"] = [f"v3{tag}_{i:05d}" for i in site_labels(rr)]
    st = pd.read_parquet(V3 + f"/sites_v3_{tag}.parquet")
    # sanity: recomputed site means equal stored
    chk = rr.groupby("site_id").log_rs.mean(); assert np.allclose(chk.loc[st.site_id].values, st.log_rs.values)
    eu = st[(st.continent == "Europe") & ~st.site_id.isin(edrop)]
    eu_recs = rr[rr.site_id.isin(eu.site_id)]
    res = {"n_test_sites": len(eu)}
    for f in ["training_features_v2.parquet", "training_features_v1_real_c6450a7.parquet"]:
        t = pd.read_parquet(P + f)
        # exact record overlap
        shared = eu_recs[eu_recs.rec_id.isin(set(t.site_id))]
        # spatial
        tree = BallTree(np.radians(t[["latitude", "longitude"]].values), metric="haversine")
        dist, ind = tree.query(np.radians(eu[["lat", "lon"]].values), k=1); dkm = dist[:, 0] * 6371.0
        # rows of the training table within 5 km of any test site
        nb = tree.query_radius(np.radians(eu[["lat", "lon"]].values), r=5.0 / 6371.0)
        rows5 = sorted(set(np.concatenate(nb).tolist()))
        sites5 = eu.site_id.values[dkm <= 5]
        tt = t.iloc[rows5]
        BIO = ["bio01","bio04","bio05","bio06","bio12","bio14","bio15","bio17"]; MOD = ["npp","lst_day","lst_night","lst_diurnal_range"]
        nF = int(tt.dropna(subset=["log_rs_annual"] + BIO).shape[0])
        nFNPP = int(tt.dropna(subset=["log_rs_annual"] + BIO + MOD).shape[0]) if "npp" in t.columns else None
        res[f] = dict(n_test_sites_sharing_exact_record=int(shared.site_id.nunique()), n_training_rows_shared_exact=int(shared.rec_id.nunique()),
                      n_test_sites_within_1km=int((dkm <= 1).sum()), n_test_sites_within_5km=int((dkm <= 5).sum()),
                      n_test_sites_within_10km=int((dkm <= 10).sum()), n_training_rows_within_5km=len(rows5),
                      of_which_in_F_rows=nF, of_which_in_FNPP_rows=nFNPP,
                      countries_of_sites_within_5km=eu[dkm <= 5].country.value_counts().to_dict(),
                      training_rows_within5_regions=tt.region.value_counts().to_dict())
    out[tag] = res
print(json.dumps(out, indent=1))
