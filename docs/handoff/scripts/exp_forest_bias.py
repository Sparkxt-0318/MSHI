"""N2b — How much does the plot/pixel forest mismatch bias an upscaled total?
Estimators over the MODIS footprint (Asia box + US box), 0.5 deg cells, forest fraction f from MCD12Q1 2023 (0.05 deg):
  A  climate-only, trained on plots (implicitly assumes the plots' ~69% forest mix everywhere)
  B  climate + PIXEL forest flag (what a land-cover-aware map does), applied with cell forest fraction f
  C  climate + PLOT forest flag (post-stratified): Rs = f * Rs_forest + (1 - f) * Rs_nonforest
Inflation = A/C - 1 and B/C - 1. Duan smearing for log back-transformation. Bootstrap over sites for CIs.
Also: attenuation — plot-flag vs pixel-flag coefficients.
"""
import json, sys
import numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf

FEAT, DL, REPO, OUT = sys.argv[1:5]
LC = f"{REPO}/data/raw/modis/landcover_igbp_2023.tif"; WC = lambda i: f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif"
rng = np.random.default_rng(0)


def samp(path, lon, lat):
    with rasterio.open(path) as s:
        return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)


d = pd.read_parquet(FEAT)
rep = {"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest", "Mixed forests": "Forest"}
d["plot_forest"] = d.ecosystem.replace(rep).eq("Forest").astype(int)
d["lnP"] = np.log(d.bio12)
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d = d[inbox & d.continent.isin(["Asia", "North America"])].dropna(subset=["log_rs", "bio01", "lnP"]).copy()
code = samp(LC, d.lon.values, d.lat.values)
d = d[(code > 0)].copy(); code = code[code > 0]
d["pixel_forest"] = np.isin(code, [1, 2, 3, 4, 5]).astype(int)

# grid of 0.5 deg cells with forest fraction, vegetated/land only (exclude water 17, snow 15, barren 16, urban 13)
cells = []
for (x0, x1, y0, y1) in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    lon, lat = np.meshgrid(np.arange(x0 + 0.025, x1, 0.05), np.arange(y0 + 0.025, y1, 0.05))
    with rasterio.open(LC) as s:
        win = rasterio.windows.from_bounds(x0, y0, x1, y1, s.transform)
        arr = s.read(1, window=win)
    ny, nx = arr.shape
    lat_c = y1 - (np.arange(ny) + 0.5) * 0.05; lon_c = x0 + (np.arange(nx) + 0.5) * 0.05
    LON, LAT = np.meshgrid(lon_c, lat_c)
    df = pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "c": arr.ravel()})
    df = df[(df.c > 0) & ~df.c.isin([13, 15, 16, 17])]
    df["cell_x"] = np.floor(df.lon / 0.5); df["cell_y"] = np.floor(df.lat / 0.5); df["f"] = df.c.isin([1, 2, 3, 4, 5])
    g = df.groupby(["cell_x", "cell_y"]).agg(f=("f", "mean"), n=("f", "size")).reset_index()
    g = g[g.n >= 20]; g["lon"] = g.cell_x * 0.5 + 0.25; g["lat"] = g.cell_y * 0.5 + 0.25
    g["box"] = "Asia" if x0 == 25 else "NA"
    cells.append(g)
g = pd.concat(cells, ignore_index=True)
for i, k in [(1, "bio01"), (12, "bio12")]:
    v = samp(WC(i), g.lon.values, g.lat.values); g[k] = np.where(v < -1e30, np.nan, v)
g = g.dropna(subset=["bio01", "bio12"]); g["lnP"] = np.log(g.bio12.clip(lower=1))
g["veg_area_m2"] = (111.32e3 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * (g.n / 100.0)
g["continent"] = np.where(g.box == "Asia", "Asia", "North America")


def totals(s):
    out = {}
    mA = smf.ols("log_rs ~ bio01 + lnP + C(continent)", data=s).fit()
    mB = smf.ols("log_rs ~ bio01 + lnP + pixel_forest + C(continent)", data=s).fit()
    mC = smf.ols("log_rs ~ bio01 + lnP + plot_forest + C(continent)", data=s).fit()
    sm = {k: np.mean(np.exp(m.resid)) for k, m in [("A", mA), ("B", mB), ("C", mC)]}
    A = np.exp(mA.predict(g)) * sm["A"]
    B = g.f * np.exp(mB.predict(g.assign(pixel_forest=1))) * sm["B"] + (1 - g.f) * np.exp(mB.predict(g.assign(pixel_forest=0))) * sm["B"]
    C = g.f * np.exp(mC.predict(g.assign(plot_forest=1))) * sm["C"] + (1 - g.f) * np.exp(mC.predict(g.assign(plot_forest=0))) * sm["C"]
    for k, v in [("A", A), ("B", B), ("C", C)]:
        out[k] = float((v * g.veg_area_m2).sum() / 1e15)
    return out, mB.params.pixel_forest, mC.params.plot_forest


base, b_pix, b_plot = totals(d)
boots = []
for _ in range(500):
    s = d.iloc[rng.integers(0, len(d), len(d))]
    t, bp, bq = totals(s); boots.append((t["A"] / t["C"] - 1, t["B"] / t["C"] - 1, bp, bq))
boots = np.array(boots)
q = lambda x: [round(float(np.quantile(x, .025)), 3), round(float(np.quantile(x, .975)), 3)]
R = dict(n_sites=int(len(d)), plot_forest_share=round(float(d.plot_forest.mean()), 3), pixel_forest_share=round(float(d.pixel_forest.mean()), 3),
         landscape_forest_share_area_weighted=round(float(np.average(g.f, weights=g.veg_area_m2)), 3),
         coef_plot_forest=round(float(b_plot), 3), coef_plot_forest_ci=q(boots[:, 3]),
         coef_pixel_forest=round(float(b_pix), 3), coef_pixel_forest_ci=q(boots[:, 2]),
         totals_PgC={k: round(v, 2) for k, v in base.items()},
         inflation_A_climate_only=round(base["A"] / base["C"] - 1, 3), inflation_A_ci=q(boots[:, 0]),
         inflation_B_pixel_landcover=round(base["B"] / base["C"] - 1, 3), inflation_B_ci=q(boots[:, 1]),
         footprint_cells=int(len(g)))
json.dump(R, open(OUT, "w"), indent=1)
print(json.dumps(R, indent=1))
