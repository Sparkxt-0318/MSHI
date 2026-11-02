"""New idea N2 — plot-pixel mismatch. Rs is measured on a plot; predictors describe the pixel around it.
Q1: How often does the plot's ecosystem (SRDB Ecosystem_type, site mode) differ from the MODIS IGBP class of its pixel?
Q2: Given climate, how different is Rs between plot ecosystem types (forest / grassland / agriculture / other)?
Q3: Composition bias: SRDB plot composition vs landscape composition within the same climate envelope
    (pixels from MCD12Q1 2023, climate peers). Post-stratified (landscape-weighted) mean Rs vs naive plot mean.
Q4: Does knowing the PLOT type (not available to maps) vs the PIXEL type (what maps use) improve prediction,
    within and across continents (OLS log Rs ~ T + lnP [+ type dummies])?
"""
import json, sys
import numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree
import statsmodels.formula.api as smf
from sklearn.metrics import r2_score

FEAT, DL, REPO, OUT = sys.argv[1:5]
LC = f"{REPO}/data/raw/modis/landcover_igbp_2023.tif"; WC = lambda i: f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif"
rng = np.random.default_rng(0)


def samp(path, lon, lat):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)
    return v


def igbp_group(c):
    c = np.asarray(c)
    return np.select([np.isin(c, [1, 2, 3, 4, 5]), np.isin(c, [8, 9]), np.isin(c, [10]), np.isin(c, [12, 14]), np.isin(c, [6, 7])],
                     ["Forest", "Savanna", "Grassland", "Agriculture", "Shrubland"], "Other")


d = pd.read_parquet(FEAT)
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
                                 "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
                                 "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"})
d["ptype"] = np.where(d.ptype.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), d.ptype, "Other")
d["lnP"] = np.log(d.bio12)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d["pixel_code"] = np.where(inbox, samp(LC, d.lon.values, d.lat.values), np.nan)
d["pixel"] = np.where(d.pixel_code.isna() | (d.pixel_code == 0), "NA", igbp_group(d.pixel_code.fillna(0)))
R = {}
s = d[d.pixel != "NA"]
R["Q1_n"] = int(len(s))
R["Q1_crosstab_plot_x_pixel"] = pd.crosstab(s.ptype, s.pixel).to_dict()
R["Q1_forest_share"] = dict(plot=round(float((s.ptype == "Forest").mean()), 3), pixel=round(float((s.pixel == "Forest").mean()), 3))
R["Q1_agreement_forest_vs_not"] = round(float(((s.ptype == "Forest") == (s.pixel == "Forest")).mean()), 3)
R["Q1_plot_forest_pixel_nonforest"] = int(((s.ptype == "Forest") & (s.pixel != "Forest")).sum())

# Q2 plot-type effect given climate (all continents)
a = d.dropna(subset=["log_rs", "bio01", "lnP"])
m = smf.ols("log_rs ~ bio01 + lnP + C(ptype, Treatment('Forest')) + C(continent)", data=a).fit(cov_type="HC3")
R["Q2_plot_type_effects_vs_forest_log"] = {k.split("]")[0].split("T.")[-1]: dict(coef=round(float(v), 3), p=round(float(m.pvalues[k]), 4))
                                           for k, v in m.params.items() if "plot" in k}
R["Q2_n"] = int(len(a))
mp = smf.ols("log_rs ~ bio01 + lnP + C(pixel) + C(continent)", data=s.dropna(subset=["log_rs", "bio01", "lnP"])).fit(cov_type="HC3")
R["Q2_pixel_type_effects_log"] = {k.split("]")[0].split("T.")[-1]: dict(coef=round(float(v), 3), p=round(float(mp.pvalues[k]), 4))
                                  for k, v in mp.params.items() if "pixel" in k}

# Q4 prediction: plot type vs pixel type, within-continent CV and Asia->NA / Asia->Europe
def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        mm = np.isin(b, vb); yield np.where(~mm)[0], np.where(mm)[0]
forms = {"climate": "log_rs ~ bio01 + lnP", "climate+plot_type": "log_rs ~ bio01 + lnP + C(ptype)", "climate+pixel_type": "log_rs ~ bio01 + lnP + C(pixel)"}
Q4 = {}
for name, f in forms.items():
    data = s if "pixel" in name else d
    data = data.dropna(subset=["log_rs", "bio01", "lnP"])
    for cont in ["Asia", "North America"]:
        u = data[data.continent == cont].reset_index(drop=True); p = np.full(len(u), np.nan)
        for tr, va in folds(u):
            try:
                p[va] = smf.ols(f, data=u.iloc[tr]).fit().predict(u.iloc[va])
            except Exception:
                pass
        ok = np.isfinite(p)
        Q4[f"{name}|within {cont}"] = round(float(r2_score(u.log_rs[ok], p[ok])), 3)
    tr = data[data.continent == "Asia"]
    for te in ["North America", "Europe"]:
        tt = data[(data.continent == te) & data.ptype.isin(tr.ptype.unique())]
        if "pixel" in name: tt = tt[tt.pixel.isin(tr.pixel.unique())]
        if len(tt) < 20: continue
        Q4[f"{name}|Asia->{te}"] = round(float(r2_score(tt.log_rs, smf.ols(f, data=tr).fit().predict(tt))), 3)
R["Q4_r2"] = Q4

# Q3 composition: plot composition vs landscape composition within climate envelope of the sites (Asia+NA boxes)
comp = {}
for reg, (x0, x1, y0, y1), cont in [("Asia", (25, 180, -10, 80), "Asia"), ("NA", (-125, -66, 24, 50), "North America")]:
    n = 300000
    p = pd.DataFrame({"lon": rng.uniform(x0, x1, n), "lat": np.degrees(np.arcsin(rng.uniform(np.sin(np.radians(y0)), np.sin(np.radians(y1)), n)))})
    p["code"] = samp(LC, p.lon.values, p.lat.values); p = p[(p.code > 0) & (p.code != 17) & (p.code != 15) & (p.code != 13)]
    for i, k in [(1, "bio01"), (12, "bio12")]:
        v = samp(WC(i), p.lon.values, p.lat.values); p[k] = np.where(v < -1e30, np.nan, v)
    p = p.dropna(); p["lnP"] = np.log(p.bio12.clip(lower=1)); p["grp"] = igbp_group(p.code)
    ss = s[(s.continent == cont)].dropna(subset=["bio01", "lnP"])
    cols = ["bio01", "lnP"]; mu, sd = p[cols].mean(), p[cols].std()
    _, idx = cKDTree(((p[cols] - mu) / sd).values).query(((ss[cols] - mu) / sd).values, k=200)
    land = pd.Series(np.asarray(p.grp, dtype=object)[idx].ravel()).value_counts(normalize=True)
    comp[reg] = dict(plot_share=ss.ptype.value_counts(normalize=True).round(3).to_dict(),
                     pixel_share_at_sites=ss.pixel.value_counts(normalize=True).round(3).to_dict(),
                     landscape_share_in_site_climates=land.round(3).to_dict())
R["Q3_composition"] = comp
json.dump(R, open(OUT, "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
