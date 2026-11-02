"""New idea N1 — preferential site selection within climate space.
Q1: Are Rs measurement sites greener (higher MODIS NPP) and more often forested than the land with the same climate?
    Each site's NPP is ranked among its k nearest 'climate peers' (random land pixels, same region, standardised
    bio01, ln bio12, bio04, bio15). Under representative sampling the ranks are Uniform(0,1) (median 0.5).
Q2: At a given climate, does Rs rise with NPP? (partial slope from pooled site regression)
Q3: How much does this inflate a climate-only upscaled total? Compare, over the MODIS footprint at 0.5 deg,
    a climate-only model (implicitly assumes 'measured-site' productivity) with a climate+NPP model fed the
    land's actual NPP. Both trained on the same sites.
Uses the committed GEE MODIS NPP raster (0.05 deg, 2020-2024 mean; Asia + US + part of Oceania footprint) and
MCD12Q1 2023 IGBP for peers AND sites, so site and landscape values come from the same product and resolution.
"""
import json, sys
import numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree
from sklearn.linear_model import LinearRegression
import statsmodels.formula.api as smf

FEAT, DL, REPO, OUT = sys.argv[1:5]
NPP = f"{REPO}/data/raw/modis/npp_2020_2024_mean.tif"; LC = f"{REPO}/data/raw/modis/landcover_igbp_2023.tif"
WC = lambda i: f"{DL}/worldclim/2.5m/wc2.1_2.5m_bio_{i}.tif"
rng = np.random.default_rng(0)


def samp(path, lon, lat):
    with rasterio.open(path) as s:
        v = np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)
        if s.nodata is not None: v[v == s.nodata] = np.nan
    return v


def climate(df):
    for i, k in [(1, "bio01"), (4, "bio04"), (12, "bio12"), (15, "bio15")]:
        v = samp(WC(i), df.lon.values, df.lat.values); df[k] = np.where(v < -1e30, np.nan, v)
    df["lnP"] = np.log(df.bio12.clip(lower=1)); return df


sites = pd.read_parquet(FEAT)
sites = sites[sites.continent.isin(["Asia", "North America"])].copy()
sites["npp_g"] = samp(NPP, sites.lon.values, sites.lat.values)
sites["igbp"] = samp(LC, sites.lon.values, sites.lat.values)
sites["region"] = np.where(sites.continent == "Asia", "Asia", "NA")
box = {"Asia": (25, 180, -10, 80), "NA": (-125, -66, 24, 50)}
sites = sites[[(box[r][0] <= lo <= box[r][1]) and (box[r][2] <= la <= box[r][3]) for r, lo, la in zip(sites.region, sites.lon, sites.lat)]]

R = {"n_sites": {}, "Q1": {}}
peers_all = {}
for reg, (x0, x1, y0, y1) in box.items():
    n = 400000
    p = pd.DataFrame({"lon": rng.uniform(x0, x1, n), "lat": np.degrees(np.arcsin(rng.uniform(np.sin(np.radians(y0)), np.sin(np.radians(y1)), n)))})
    p["npp_g"] = samp(NPP, p.lon.values, p.lat.values); p["igbp"] = samp(LC, p.lon.values, p.lat.values)
    p = p[np.isfinite(p.npp_g) & (p.npp_g > 0)]
    p = climate(p).dropna(subset=["bio01", "bio04", "lnP", "bio15"])
    peers_all[reg] = p
    s = sites[(sites.region == reg)].copy()
    s = s[np.isfinite(s.npp_g) & (s.npp_g > 0)].dropna(subset=["bio01", "bio04", "bio12", "bio15"])
    s["lnP"] = np.log(s.bio12)
    cols = ["bio01", "lnP", "bio04", "bio15"]; mu, sd = p[cols].mean(), p[cols].std()
    tree = cKDTree(((p[cols] - mu) / sd).values)
    dist, idx = tree.query(((s[cols] - mu) / sd).values, k=500)
    pnpp = p.npp_g.values[idx]; pfor = np.isin(p.igbp.values[idx], [1, 2, 3, 4, 5])
    s["npp_rank"] = (pnpp < s.npp_g.values[:, None]).mean(1)
    s["peer_npp_median"] = np.median(pnpp, 1)
    s["peer_forest_frac"] = pfor.mean(1)
    s["site_forest"] = s.igbp.isin([1, 2, 3, 4, 5])
    # bootstrap CI on median rank
    bs = [np.median(rng.choice(s.npp_rank.values, len(s))) for _ in range(2000)]
    R["n_sites"][reg] = len(s)
    R["Q1"][reg] = dict(median_rank=round(float(s.npp_rank.median()), 3), median_rank_ci=[round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)],
                        frac_above_peer_median=round(float((s.npp_rank > 0.5).mean()), 3),
                        site_npp_over_peer_median_ratio=round(float(np.median(s.npp_g / s.peer_npp_median)), 3),
                        site_forest_frac=round(float(s.site_forest.mean()), 3), peer_forest_frac=round(float(s.peer_forest_frac.mean()), 3),
                        median_peer_dist_sd=round(float(np.median(dist[:, -1])), 3))
    sites.loc[s.index, "npp_rank"] = s.npp_rank; sites.loc[s.index, "peer_npp_median"] = s.peer_npp_median
    sites.loc[s.index, "lnP"] = s.lnP

# Q2: within-climate Rs ~ NPP slope (log-log), sites with valid npp
s = sites.dropna(subset=["npp_g", "log_rs", "bio01", "lnP"]).copy(); s = s[s.npp_g > 0]
s["lnNPP"] = np.log(s.npp_g)
m = smf.ols("log_rs ~ bio01 + lnP + bio04 + bio15 + lnNPP + C(region)", data=s).fit(cov_type="HC3")
R["Q2_lnNPP_slope"] = dict(coef=round(float(m.params.lnNPP), 3), ci=[round(float(x), 3) for x in m.conf_int().loc["lnNPP"]],
                           p=float(m.pvalues.lnNPP), n=int(len(s)))
m_rank = smf.ols("log_rs ~ bio01 + lnP + bio04 + bio15 + npp_rank + C(region)", data=s.dropna(subset=["npp_rank"])).fit(cov_type="HC3")
R["Q2_npp_rank_slope"] = dict(coef=round(float(m_rank.params.npp_rank), 3), ci=[round(float(x), 3) for x in m_rank.conf_int().loc["npp_rank"]], p=float(m_rank.pvalues.npp_rank))

# Q3: upscaled totals over the footprint (0.5 deg cells inside the two boxes, vegetated)
X_cl = ["bio01", "lnP", "bio04", "bio15"]
mc = LinearRegression().fit(s[X_cl], s.log_rs); mn = LinearRegression().fit(s[X_cl + ["lnNPP"]], s.log_rs)
res_c = s.log_rs - mc.predict(s[X_cl]); res_n = s.log_rs - mn.predict(s[X_cl + ["lnNPP"]])
smear_c, smear_n = np.mean(np.exp(res_c)), np.mean(np.exp(res_n))  # Duan smearing for log retransformation
out = {}
for reg, p in peers_all.items():
    q = p.copy(); q["cell"] = list(zip(np.floor(q.lon / 0.5), np.floor(q.lat / 0.5)))
    g = q.groupby("cell").agg(lon=("lon", "mean"), lat=("lat", "mean"), bio01=("bio01", "mean"), lnP=("lnP", "mean"),
                              bio04=("bio04", "mean"), bio15=("bio15", "mean"), npp_g=("npp_g", "mean"), n=("npp_g", "size"))
    g = g[g.n >= 3]; g["lnNPP"] = np.log(g.npp_g)
    area = (111.32 * 0.5) ** 2 * np.cos(np.radians(g.lat)) * 1e6  # m2
    tot_c = float((np.exp(mc.predict(g[X_cl])) * smear_c * area).sum() / 1e15)
    tot_n = float((np.exp(mn.predict(g[X_cl + ["lnNPP"]])) * smear_n * area).sum() / 1e15)
    out[reg] = dict(cells=int(len(g)), climate_only_PgC=round(tot_c, 2), climate_plus_landscape_NPP_PgC=round(tot_n, 2),
                    inflation_pct=round(100 * (tot_c / tot_n - 1), 1))
R["Q3_upscaled_totals_vegetated_footprint"] = out
json.dump(R, open(OUT, "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
