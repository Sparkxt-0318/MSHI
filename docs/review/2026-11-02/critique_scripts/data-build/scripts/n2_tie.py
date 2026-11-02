"""Reproduce exp_plot_pixel Q1 (no climate needed) from the rebuilt QC site table + the repo GEE IGBP raster,
then test sensitivity of the plot forest share to the alphabetical mode tie-break in build_sites_v3.to_sites."""
import sys, numpy as np, pandas as pd, rasterio
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V3, LC = sys.argv[1], sys.argv[2]
st = pd.read_parquet(f"{V3}/sites_v3_qc.parquet")
CW = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
      "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
      "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"}
def ptype(e):
    p = pd.Series(e).replace(CW)
    return np.where(p.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), p, "Other")
def igbp_group(c):
    c = np.asarray(c)
    return np.select([np.isin(c, [1, 2, 3, 4, 5]), np.isin(c, [8, 9]), np.isin(c, [10]), np.isin(c, [12, 14]), np.isin(c, [6, 7])],
                     ["Forest", "Savanna", "Grassland", "Agriculture", "Shrubland"], "Other")
with rasterio.open(LC) as s:
    code = np.array([x[0] for x in s.sample(list(zip(st.lon, st.lat)))], float)
inbox = (st.lon.between(25, 180) & st.lat.between(-10, 80)) | (st.lon.between(-125, -66) & st.lat.between(24, 50))
code = np.where(inbox, code, np.nan)
pix = np.where(np.isnan(code) | (code == 0), "NA", igbp_group(np.nan_to_num(code)))
st["ptype"] = ptype(st.ecosystem); st["pixel"] = pix
s = st[st.pixel != "NA"]
print(f"Q1 reproduced: n={len(s)} plot forest share={np.mean(s.ptype=='Forest'):.3f} pixel forest share={np.mean(s.pixel=='Forest'):.3f}  (handoff: n=624, 0.694, 0.304)")
# tie-break sensitivity: rebuild record->site map for QC records and recompute site plot type under alternative rules
r = pd.read_parquet(f"{V3}/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab; qc["pt"] = ptype(qc.Ecosystem_type.fillna("NA_"))
qc.loc[qc.Ecosystem_type.isna(), "pt"] = np.nan
alt = {}
for sid, g in qc.groupby("site"):
    vc = g.pt.dropna().value_counts()
    if len(vc) == 0: alt[sid] = ("Other", "Other", 0.0); continue
    top = vc[vc == vc.iloc[0]].index
    alt[sid] = ("Forest" if "Forest" in top else top[0], sorted([t for t in top if t != "Forest"])[0] if any(t != "Forest" for t in top) else "Forest",
                float((g.pt == "Forest").mean()))
alt = pd.DataFrame.from_dict(alt, orient="index", columns=["tie_forest", "tie_nonforest", "rec_forest_frac"])
# align: site ids in sites_v3_qc are 'v3qc_{label:05d}' with the same connected_components labels
alt.index = [f"v3qc_{i:05d}" for i in alt.index]
s2 = s.join(alt, on="site_id")
print(f"  ties->Forest:     plot forest share={np.mean(s2.tie_forest=='Forest'):.3f}")
print(f"  ties->non-Forest: plot forest share={np.mean(s2.tie_nonforest=='Forest'):.3f}")
print(f"  record-weighted forest fraction (mean over sites): {s2.rec_forest_frac.mean():.3f}")
print(f"  sites in Q1 set whose records are mixed forest/non-forest: {int(((s2.rec_forest_frac>0)&(s2.rec_forest_frac<1)).sum())} of {len(s2)}")
