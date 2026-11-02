import sys, json, numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf
from sklearn.metrics import r2_score
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
S, G, REC, LC = sys.argv[1:5]
d = pd.read_parquet(S).dropna(subset=["log_rs", "bio01", "lnP"]).reset_index(drop=True)
d["na"] = (d.continent == "North America").astype(float)
def samp(path, lon, lat):
    with rasterio.open(path) as s: return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)
# (E) parameter names in exp_plot_pixel.py Q2 (filter `"plot" in k`)
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
    "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"})
m = smf.ols("log_rs ~ bio01 + lnP + C(ptype, Treatment('Forest')) + C(continent)", data=d).fit(cov_type="HC3")
print("(E) Q2 param names:", [k for k in m.params.index if "ptype" in k][:2], "-> contain 'plot'?", any("plot" in k for k in m.params.index))
# (G) Duan smearing contribution to N2b inflation
y = d.log_rs.values; Z = np.column_stack([np.ones(len(d)), d.bio01, d.lnP, d.na])
bA = np.linalg.lstsq(Z, y, rcond=None)[0]; Zc = np.column_stack([Z, d.plot_forest]); bC = np.linalg.lstsq(Zc, y, rcond=None)[0]
rA, rC = y - Z @ bA, y - Zc @ bC
print("(G) smearing A, C, ratio:", round(np.mean(np.exp(rA)), 4), round(np.mean(np.exp(rC)), 4), round(np.mean(np.exp(rA)) / np.mean(np.exp(rC)), 4))
print("    class-specific smearing C (forest, non-forest):", round(np.mean(np.exp(rC[d.plot_forest == 1])), 4), round(np.mean(np.exp(rC[d.plot_forest == 0])), 4),
      " residual SD forest/non-forest:", round(rC[d.plot_forest == 1].std(), 3), round(rC[d.plot_forest == 0].std(), 3))
g0 = pd.read_parquet(G)
inc = [f"n{k}" for k in range(1, 18) if k not in (13, 15, 16, 17)]
g0["n"] = g0[inc].sum(axis=1); g = g0[g0.n >= 20].dropna(subset=["bio01", "bio12"]).copy()
g["lnP"] = np.log(g.bio12.clip(lower=1)); g["na"] = (g.cont == "North America").astype(float)
g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0); g["f"] = g[["n1", "n2", "n3", "n4", "n5"]].sum(axis=1) / g.n
Gz = np.column_stack([np.ones(len(g)), g.bio01, g.lnP, g.na])
A = (np.exp(Gz @ bA) * np.mean(np.exp(rA)) * g.area).sum()
sF, sN = np.mean(np.exp(rC[d.plot_forest == 1])), np.mean(np.exp(rC[d.plot_forest == 0]))
C1 = ((g.f * np.exp(Gz @ bC[:4] + bC[4]) + (1 - g.f) * np.exp(Gz @ bC[:4])) * np.mean(np.exp(rC)) * g.area).sum()
C2 = ((g.f * np.exp(Gz @ bC[:4] + bC[4]) * sF + (1 - g.f) * np.exp(Gz @ bC[:4]) * sN) * g.area).sum()
print(f"    inflation with pooled smearing {A / C1 - 1:.4f}; with class-specific smearing {A / C2 - 1:.4f}")
# (I) area dropped by n>=20 rule (N2b footprint), counting included pixels
gg = g0.copy(); w = np.cos(np.radians(gg.lat)) * gg.n
print(f"(I) included-pixel area in cells with n<20: {w[gg.n < 20].sum() / w.sum():.4f}")
# (L) study year vs pixel agreement among forest plots
f = d[d.plot_forest == 1]
print("(L) forest plots: median year_med in forest pixel vs non-forest pixel:", f[f.code.isin([1,2,3,4,5])].year_med.median(), f[~f.code.isin([1,2,3,4,5])].year_med.median(),
      " n with year:", int(f.year_med.notna().sum()))
for lo, hi in [(1960, 2000), (2000, 2010), (2010, 2030)]:
    ff = f[(f.year_med >= lo) & (f.year_med < hi)]
    print(f"    year [{lo},{hi}): n={len(ff)}  in IGBP1-5: {ff.code.isin([1,2,3,4,5]).mean():.3f}  in IGBP1-5,8: {ff.code.isin([1,2,3,4,5,8]).mean():.3f}")
# (D) exp_plot_pixel Q4: within-NA CV R2 of the climate-only model on the pixel-model sample (CONUS box) vs all NA (not available)
def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        mm = np.isin(b, vb); yield np.where(~mm)[0], np.where(mm)[0]
def igbp_group(c):
    c = np.asarray(c)
    return np.select([np.isin(c, [1, 2, 3, 4, 5]), np.isin(c, [8, 9]), np.isin(c, [10]), np.isin(c, [12, 14]), np.isin(c, [6, 7])],
                     ["Forest", "Savanna", "Grassland", "Agriculture", "Shrubland"], "Other")
d["pixel"] = igbp_group(d.code)
for cont in ["Asia", "North America"]:
    u = d[d.continent == cont].reset_index(drop=True)
    for nm, fm in [("climate", "log_rs ~ bio01 + lnP"), ("climate+pixel_type", "log_rs ~ bio01 + lnP + C(pixel)"), ("climate+plot_type", "log_rs ~ bio01 + lnP + C(ptype)")]:
        p = np.full(len(u), np.nan); fails = 0
        for tr, va in folds(u):
            try: p[va] = smf.ols(fm, data=u.iloc[tr]).fit().predict(u.iloc[va])
            except Exception: fails += 1
        ok = np.isfinite(p)
        print(f"(D) {cont:14s} {nm:20s} same in-box sample n={len(u)} scored={int(ok.sum())} failed_folds={fails} R2={r2_score(u.log_rs[ok], p[ok]):.3f}")
# (M) record-level pixel check: QC records labelled Forest, pixel at the record's own coordinates vs at the site centroid
r = pd.read_parquet(REC)
base = r[~r.f_offland & ~r.f_coord]; qc = base[~(base.f_method | base.f_quality | base.f_coverage | base.f_ecosys | base.f_dup)].reset_index(drop=True)
X = np.radians(qc[["lat", "lon"]].values); nb = BallTree(X, metric="haversine").query_radius(X, r=5.0 / 6371.0)
rows = np.concatenate([[i] * len(n) for i, n in enumerate(nb)]); cols = np.concatenate(nb)
_, lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(qc), len(qc))), directed=False)
qc["site"] = lab
cent = qc.groupby("site")[["lat", "lon"]].transform("mean"); qc["clat"], qc["clon"] = cent.lat, cent.lon
inb = ((qc.lon.between(25, 180) & qc.lat.between(-10, 80)) | (qc.lon.between(-125, -66) & qc.lat.between(24, 50))) & qc.continent.isin(["Asia", "North America"])
fr = qc[inb & qc.Ecosystem_type.isin(["Forest", "Evergreen needleleaf forest", "Deciduous broadleaf forest", "Evergreen broadleaf forest", "Mixed forests"])].copy()
fr["code_rec"] = samp(LC, fr.lon.values, fr.lat.values); fr["code_cent"] = samp(LC, fr.clon.values, fr.clat.values)
print(f"(M) forest-labelled QC records in box: {len(fr)}; IGBP1-5 at record coords {fr.code_rec.isin([1,2,3,4,5]).mean():.3f}, at site centroid {fr.code_cent.isin([1,2,3,4,5]).mean():.3f};"
      f" pixel differs record vs centroid: {(fr.code_rec != fr.code_cent).mean():.3f}")
# extent of 5-km connected-component sites (max pairwise distance proxy: max distance from centroid)
dk = 6371 * 2 * np.arcsin(np.sqrt(np.sin(np.radians(qc.lat - qc.clat) / 2) ** 2 + np.cos(np.radians(qc.lat)) * np.cos(np.radians(qc.clat)) * np.sin(np.radians(qc.lon - qc.clon) / 2) ** 2))
ext = dk.groupby(qc.site).max()
print("    site max record-to-centroid distance (km) quantiles 50/90/99/max:", np.round(np.quantile(ext, [.5, .9, .99, 1]), 2))
