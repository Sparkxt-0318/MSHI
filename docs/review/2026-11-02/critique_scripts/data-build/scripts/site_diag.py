import sys, numpy as np, pandas as pd
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
V3 = sys.argv[1]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
r = pd.read_parquet(f"{V3}/records_v3.parquet")
base = r[~r.f_offland & ~r.f_coord]
qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)]
def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2); dl = np.radians(lon2 - lon1); dp = p2 - p1
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))
def label(rr):
    X = np.radians(rr[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5 / 6371)
    rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
    _, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(rr), len(rr))), directed=False)
    return rr.assign(site=lab)
SRDB_TYPES = {"Forest", "Grassland", "Agriculture", "Wetland", "Shrubland", "Desert", "Savanna", "Urban", "Tundra", "Bare"}
for tag, rr in [("qc", qc), ("repo", base)]:
    rr = label(rr.reset_index(drop=True))
    res = []
    for sid, g in rr.groupby("site"):
        la, lo = g.lat.values, g.lon.values
        u = np.unique(np.c_[la, lo], axis=0)
        if len(u) > 1:
            D = hav(u[:, None, 0], u[:, None, 1], u[None, :, 0], u[None, :, 1]); dmax = D.max()
        else: dmax = 0.0
        cl, co = la.mean(), lo.mean()
        dc = hav(cl, co, la, lo).max()
        e = g.Ecosystem_type.dropna()
        vc = e.value_counts()
        tie = len(vc) > 1 and vc.iloc[0] == vc.iloc[1]
        mode_pick = e.mode().iat[0] if len(e) else np.nan
        cont_vc = g.continent.value_counts(); ctie = len(cont_vc) > 1 and cont_vc.iloc[0] == cont_vc.iloc[1]
        res.append(dict(site=sid, n=len(g), n_coords=len(u), dmax=dmax, dcent=dc, eco=mode_pick, eco_tie=tie,
                        tie_set="|".join(sorted(vc[vc == vc.iloc[0]].index)) if tie else "", n_types=len(vc),
                        cosore_eco=(mode_pick not in SRDB_TYPES) if isinstance(mode_pick, str) else False,
                        n_cos=int((g.src == "cosore").sum()), n_srdb=int((g.src == "srdb").sum()),
                        cont=g.continent.mode().iat[0], cont_tie=ctie, conts="|".join(sorted(cont_vc.index)),
                        lonspan=lo.max() - lo.min()))
    S = pd.DataFrame(res)
    print(f"\n===== {tag}: {len(S)} sites")
    print("sites with >1 distinct coordinate:", int((S.n_coords > 1).sum()))
    for th in [5, 10, 20, 50]:
        print(f"  max pairwise record distance > {th} km: {int((S.dmax > th).sum())} sites ({int(S[S.dmax > th].n.sum())} records)")
    print("  largest chains:"); print(S.sort_values("dmax", ascending=False).head(8)[["site", "n", "n_coords", "dmax", "dcent", "cont", "eco"]].round(1).to_string())
    print("  antimeridian-spanning sites (lon span > 180):", int((S.lonspan > 180).sum()))
    print("  sites with records on >1 continent:", int((S.conts.str.contains(r"\|")).sum()), " continent ties:", int(S.cont_tie.sum()))
    print("  ecosystem ties:", int(S.eco_tie.sum()), "; tie sets:", S[S.eco_tie].tie_set.value_counts().to_dict())
    print("  ties where Forest is in the tied set but mode picked non-Forest:", int((S.eco_tie & S.tie_set.str.contains("Forest") & (S.eco != "Forest")).sum()))
    print("  sites whose ecosystem is a COSORE IGBP string:", int(S.cosore_eco.sum()), S[S.cosore_eco].eco.value_counts().to_dict())
    print("  ... of which also contain SRDB records:", int((S.cosore_eco & (S.n_srdb > 0)).sum()))
    print("  COSORE-containing sites whose mode is an SRDB type (COSORE label outvoted):", int(((S.n_cos > 0) & ~S.cosore_eco).sum()))
    S.to_csv(f"{V3}/../site_diag_{tag}.csv", index=False)
    # per-continent mix
    print("  COSORE-string ecosystems by continent:", S[S.cosore_eco].groupby("cont").eco.value_counts().to_dict())
