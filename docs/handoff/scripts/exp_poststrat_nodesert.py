"""N2c — multi-class post-stratification. Plot classes (SRDB Ecosystem_type): Forest, Grassland, Agriculture,
Shrubland, Savanna, Desert. Landscape classes from MCD12Q1 IGBP at 0.05 deg, two crosswalks for woody savanna (8):
  X1: 8 -> Forest (canopy 30-60%)        X2: 8 -> Savanna
Others: 1-5 Forest, 6-7 Shrubland, 9 Savanna, 10 Grassland, 12/14 Agriculture, 16 Desert (barren); 11/13/15/17 excluded.
Estimators: A climate-only (plots' own mix) vs C post-stratified sum_k f_k * Rs_k(climate). Inflation = A/C - 1.
Bootstrap CIs over sites. Asia + US boxes (MODIS footprint).
"""
import json, sys
import numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf

FEAT, DL, REPO, OUT = sys.argv[1:5]
LC = f"{REPO}/data/raw/modis/landcover_igbp_2023.tif"; WC = lambda i: f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif"
CL = ["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna"]
rng = np.random.default_rng(0)


def samp(path, lon, lat):
    with rasterio.open(path) as s:
        return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)


d = pd.read_parquet(FEAT)
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
       "Mixed forests": "Forest", "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"}
d["pt"] = d.ecosystem.replace(rep)
d["lnP"] = np.log(d.bio12)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d = d[inbox & d.continent.isin(["Asia", "North America"]) & d.pt.isin(CL)].dropna(subset=["log_rs", "bio01", "lnP"]).copy()

frames = []
for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    with rasterio.open(LC) as s:
        arr = s.read(1, window=rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform))
    ny, nx = arr.shape
    LON, LAT = np.meshgrid(x0 + (np.arange(nx) + 0.5) * 0.05, y1 - (np.arange(ny) + 0.5) * 0.05)
    df = pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel()})
    df = df[(df.c > 0) & ~df.c.isin([11, 13, 15, 16, 17])]
    df["cx"], df["cy"] = np.floor(df.lon / 0.5), np.floor(df.lat / 0.5)
    df["cont"] = "Asia" if x0 == 25 else "North America"
    frames.append(df)
px = pd.concat(frames, ignore_index=True)


def crosswalk(c, woody):
    m = {1: "Forest", 2: "Forest", 3: "Forest", 4: "Forest", 5: "Forest", 6: "Shrubland", 7: "Shrubland", 8: woody, 9: "Savanna",
         10: "Grassland", 12: "Agriculture", 14: "Agriculture", 16: "Desert"}
    return c.map(m)


R = {"n_sites": int(len(d)), "plot_share": d.pt.value_counts(normalize=True).round(3).to_dict()}
for name, woody in [("X1_woody_savanna_as_forest", "Forest"), ("X2_woody_savanna_as_savanna", "Savanna")]:
    px["k"] = crosswalk(px.c, woody)
    frac = px.groupby(["cx", "cy", "cont", "k"]).size().unstack(fill_value=0)
    n = frac.sum(1); frac = frac.div(n, axis=0)
    g = frac.reset_index(); g["n"] = n.values; g = g[g.n >= 20]
    g["lon"], g["lat"] = g.cx * 0.5 + 0.25, g.cy * 0.5 + 0.25
    for i, k in [(1, "bio01"), (12, "bio12")]:
        v = samp(WC(i), g.lon.values, g.lat.values); g[k] = np.where(v < -1e30, np.nan, v)
    g = g.dropna(subset=["bio01", "bio12"]); g["lnP"] = np.log(g.bio12.clip(lower=1)); g["continent"] = g.cont
    g["area"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * g.n / 100.0
    land_share = {k: round(float(np.average(g[k], weights=g.area)), 3) for k in CL if k in g}

    def est(s):
        mA = smf.ols("log_rs ~ bio01 + lnP + C(continent)", data=s).fit()
        mC = smf.ols("log_rs ~ bio01 + lnP + C(continent) + C(pt, Treatment(reference='Forest'))", data=s).fit()
        tA = (np.exp(mA.predict(g)) * np.mean(np.exp(mA.resid)) * g.area).sum()
        smC = np.mean(np.exp(mC.resid)); tC = 0
        for k in CL:
            if k in g and k in set(s.pt):
                tC = tC + g[k] * np.exp(mC.predict(g.assign(pt=k))) * smC
        tC = (tC * g.area).sum()
        return tA / 1e15, tC / 1e15
    tot_A, tot_C = est(d)
    bs = []
    for _ in range(300):
        s = d.iloc[rng.integers(0, len(d), len(d))]
        if s.pt.nunique() < len(CL): continue
        a, c = est(s); bs.append(a / c - 1)
    R[name] = dict(landscape_share=land_share, climate_only_PgC=round(tot_A, 2), poststratified_PgC=round(tot_C, 2),
                   inflation=round(tot_A / tot_C - 1, 3), inflation_ci=[round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)], n_boot=len(bs))
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps(R, indent=1))
