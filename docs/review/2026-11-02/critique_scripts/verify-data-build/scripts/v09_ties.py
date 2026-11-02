"""Finding 09: site ecosystem = x.mode().iat[0] (build_sites_v3.py:98). Reproduce N2 Q1 (exp_plot_pixel.py:33-47) from the
rebuilt QC sites + repo GEE IGBP raster, then recompute the plot-forest share under alternative tie rules."""
import sys, numpy as np, pandas as pd, rasterio
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V = sys.argv[1]; LC = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/modis/landcover_igbp_2023.tif"
print("pandas mode order demo:", pd.Series(["Grassland", "Forest", "Agriculture", "Forest", "Grassland", "Agriculture"]).mode().tolist())
rec = pd.read_parquet(f"{V}/out/v3/records_v3.parquet"); st = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
base = rec[~rec.f_offland & ~rec.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab
assert (qc.groupby("site").Ecosystem_type.agg(lambda x: x.mode().iat[0] if x.notna().any() else np.nan).values.astype(str) == st.ecosystem.values.astype(str)).all()
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
       "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"}
def ptype(e):
    e = pd.Series(e).replace(rep); return np.where(e.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), e, "Other")
def ties(x):
    vc = x.value_counts(); return list(vc[vc == vc.max()].index) if len(vc) else []
tie = qc.groupby("site").Ecosystem_type.agg(ties)
nt = tie.map(len) > 1
print("QC sites with tied ecosystem modes:", int(nt.sum()), "; patterns:", tie[nt].map(lambda l: "|".join(sorted(l))).value_counts().head(6).to_dict())
# N2 Q1 reproduction
d = st.copy(); d["ptype"] = ptype(d.ecosystem)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
with rasterio.open(LC) as s: code = np.array([v[0] for v in s.sample(list(zip(d.lon, d.lat)))], float)
d["pixel_code"] = np.where(inbox, code, np.nan); ok = ~(d.pixel_code.isna() | (d.pixel_code == 0))
s = d[ok].copy(); print(f"N2 Q1 reproduction: n={len(s)}, plot forest share={np.mean(s.ptype == 'Forest'):.3f}")
# record-level class mixes within Q1 sites
qc["pt"] = ptype(qc.Ecosystem_type.values)
q1 = qc[qc.site.isin(s.index)]
mix = q1.groupby("site").pt.agg(lambda x: ((x == "Forest").any()) and ((x != "Forest").any()))
print("Q1 sites containing both forest and non-forest records:", int(mix.sum()))
frac = q1.groupby("site").pt.agg(lambda x: np.mean(x == "Forest"))
# alternative tie rules at class level (ptype of tied raw types)
def alt(site_idx, prefer_forest):
    t = tie.loc[site_idx]
    if len(t) <= 1: return s.loc[site_idx, "ptype"] == "Forest"
    cls = set(ptype(t))
    if "Forest" in cls and len(cls) > 1: return prefer_forest
    return s.loc[site_idx, "ptype"] == "Forest"
print(f"plot-forest share: as built {np.mean(s.ptype=='Forest'):.3f}; ties->non-forest {np.mean([alt(i, False) for i in s.index]):.3f}; "
      f"ties->forest {np.mean([alt(i, True) for i in s.index]):.3f}; record-weighted {frac.loc[s.index].mean():.3f}")
