import sys, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
REC, SRDB = sys.argv[1:3]
raw = pd.read_csv(SRDB, low_memory=False, usecols=["Ecosystem_type", "Rs_annual", "Manipulation", "Latitude", "Longitude"])
print("SRDB Ecosystem_type (all rows):", raw.Ecosystem_type.value_counts(dropna=False).to_dict())
r = pd.read_parquet(REC)
base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
print("QC records Ecosystem_type:", qc.Ecosystem_type.value_counts(dropna=False).to_dict())
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab
FOREST = {"Forest", "Evergreen needleleaf forest", "Deciduous broadleaf forest", "Evergreen broadleaf forest", "Mixed forests", "Deciduous needleleaf forest", "Evergreen needleleaf plantation"}
qc["is_f"] = qc.Ecosystem_type.isin(FOREST)
site = qc.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), cont=("continent", lambda x: x.mode().iat[0]),
                              mode=("Ecosystem_type", lambda x: x.mode().iat[0] if x.notna().any() else np.nan),
                              nmodes=("Ecosystem_type", lambda x: len(x.mode())), frac_f=("is_f", "mean"), n=("is_f", "size"),
                              nlab=("Ecosystem_type", lambda x: x.nunique()))
inb = ((site.lon.between(25, 180) & site.lat.between(-10, 80)) | (site.lon.between(-125, -66) & site.lat.between(24, 50))) & site.cont.isin(["Asia", "North America"])
s = site[inb]
print("in-box Asia/NA sites:", len(s), " mixed-label sites:", int((s.nlab > 1).sum()), " tied modes:", int((s.nmodes > 1).sum()))
print("forest share: site mode", round(s["mode"].isin(FOREST).mean(), 3), "| record-weighted", round(qc[qc.site.isin(s.index)].is_f.mean(), 3),
      "| site-mean of record forest fraction", round(s.frac_f.mean(), 3))
t = s[s.nmodes > 1]
print("tied sites, chosen label:", t["mode"].value_counts().to_dict(), " of which forest fraction exactly 0.5:", int((t.frac_f == 0.5).sum()))
# COSORE strings not in N2b/N2c maps: where did they go?
cos = qc[qc.src == "cosore"]
print("COSORE QC records:", cos.Ecosystem_type.value_counts().to_dict())
for lbl in ["Woody savanna", "Deciduous needleleaf forest", "Evergreen needleleaf plantation", "Grassland"]:
    for _, row in cos[cos.Ecosystem_type == lbl].iterrows():
        st = site.loc[row.site]
        print(f"  {lbl:32s} -> site mode {st['mode']!s:28s} n_rec={st.n} cont={st.cont} inbox={bool(inb.loc[row.site])}")
