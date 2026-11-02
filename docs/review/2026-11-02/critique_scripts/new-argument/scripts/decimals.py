"""Reconstruct the '>=4 decimal coordinates' check (no script in the handoff computes it).
Records -> sites with the build_sites_v3.py algorithm (QC variant), raw coordinate strings from the CSV."""
import sys, numpy as np, pandas as pd, rasterio
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.neighbors import BallTree
REC, SRDB, COS, LC, Q1 = sys.argv[1:6]
r = pd.read_parquet(REC)
raw = pd.read_csv(SRDB, dtype=str, usecols=["Latitude", "Longitude"], keep_default_na=False)
r["lat_str"] = None; r["lon_str"] = None
srdb = r.src == "srdb"
idx = r.loc[srdb, "rec_id"].str.replace("srdb_", "").astype(int).values
r.loc[srdb, "lat_str"] = raw.Latitude.values[idx]; r.loc[srdb, "lon_str"] = raw.Longitude.values[idx]
cos = pd.read_csv(COS, dtype=str)
cmap = dict(zip(cos.site_id, zip(cos.latitude, cos.longitude)))
r.loc[~srdb, "lat_str"] = [cmap[k][0] for k in r.loc[~srdb, "rec_id"]]; r.loc[~srdb, "lon_str"] = [cmap[k][1] for k in r.loc[~srdb, "rec_id"]]
# sanity: string parses to the same float
assert np.allclose(r.lat_str.astype(float), r.lat) and np.allclose(r.lon_str.astype(float), r.lon)
ndec = lambda x: x.str.split(".").str[1].fillna("").str.len()
r["ndec"] = np.minimum(ndec(r.lat_str), ndec(r.lon_str))
def dms_like(v):  # value consistent with a degrees-minutes(-seconds) conversion at >=4 decimals
    a = np.abs(v.astype(float)) * 60; b = np.abs(v.astype(float)) * 3600
    return (np.abs(a - np.round(a)) < 0.006) | (np.abs(b - np.round(b)) < 0.06)
r["dms"] = dms_like(r.lat_str) & dms_like(r.lon_str) & (r.ndec >= 4)
base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab
g = qc.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), min_ndec=("ndec", "min"), all_dms=("dms", "all"),
                           any_dms=("dms", "any"), n_rec=("ndec", "size"), n_xy=("lat", lambda x: len(set(zip(x, qc.loc[x.index, "lon"])))))
q1 = pd.read_parquet(Q1)
m = q1.merge(g, on=["lat", "lon"], how="left", validate="one_to_one")
assert m.min_ndec.notna().all(), "site match failed"
# naive decimals from the site-mean float (what a quick check on the site table would see)
m["site_ndec_float"] = np.minimum(m.lat.astype(str).str.split(".").str[1].str.len(), m.lon.astype(str).str.split(".").str[1].str.len())
F = m.ptype == "Forest"
def rep(mask, label):
    sub = m[mask & F]
    print(f"{label:62s} forest plots n={len(sub):3d}  in IGBP1-5 pixel: {(sub.pixel=='Forest').mean():.3f}  in IGBP1-5,8: {sub.pixel_code.isin([1,2,3,4,5,8]).mean():.3f}"
          f" | all plots n={mask.sum():3d} pixel-forest(1-5) {(m[mask].pixel=='Forest').mean():.3f} plot-forest {(m[mask].ptype=='Forest').mean():.3f}")
rep(np.ones(len(m), bool), "all Q1 sites")
rep(m.site_ndec_float >= 4, "site-MEAN float has >=4 decimals (naive)")
rep(m.min_ndec >= 4, "every raw record coordinate has >=4 decimals")
rep((m.min_ndec >= 4) & ~m.any_dms, "  ... and no record is DMS-like (x*60 or x*3600 integer)")
rep((m.min_ndec >= 4) & (m.n_xy == 1), "  ... and all records share one coordinate pair")
rep(m.min_ndec <= 2, "some record has <=2 decimals")
print("\nsites with >=4-dec (raw):", int((m.min_ndec >= 4).sum()), " of which DMS-like (all records):", int(((m.min_ndec >= 4) & m.all_dms).sum()),
      " any record DMS-like:", int(((m.min_ndec >= 4) & m.any_dms).sum()))
print("site-mean float >=4 dec:", int((m.site_ndec_float >= 4).sum()), " of which raw min_ndec<4:", int(((m.site_ndec_float >= 4) & (m.min_ndec < 4)).sum()))
print("multi-coordinate sites (n_xy>1):", int((m.n_xy > 1).sum()))
m.to_parquet(sys.argv[6])
