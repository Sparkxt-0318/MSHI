"""Finding 09: which Q4 folds (exp_plot_pixel.py L60-78) would raise on unseen factor levels and be silently skipped?"""
import sys, numpy as np, pandas as pd, statsmodels.formula.api as smf
from sklearn.metrics import r2_score
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import V
s = pd.read_parquet(f"{V}/out/q1_sample.parquet")
d = pd.read_parquet(f"{V}/out/sites_qc_proxy.parquet")
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
                                 "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
                                 "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"})
d["ptype"] = np.where(d.ptype.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), d.ptype, "Other")
print("all QC sites ptype by continent:\n", pd.crosstab(d.continent, d.ptype))

def folds(df, seed=42, deg=5.0, k=5):  # verbatim L60-64
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        mm = np.isin(b, vb); yield np.where(~mm)[0], np.where(mm)[0]

for cont in ["Asia", "North America"]:
    for tag, data in [("all-continent d (climate & plot-type models)", d), ("in-box s (pixel model)", s.merge(d[["site_id", "bio01", "bio12"]], on="site_id", how="left"))]:
        u = data[data.continent == cont].reset_index(drop=True)
        for i, (tr, va) in enumerate(folds(u)):
            miss_p = set(u.ptype.iloc[va]) - set(u.ptype.iloc[tr])
            miss_x = (set(u.pixel.iloc[va]) - set(u.pixel.iloc[tr])) if "pixel" in u else set()
            if miss_p or miss_x:
                print(f"{cont} | {tag} | n={len(u)} | fold {i}: {len(va)} val sites; unseen ptype {miss_p}; unseen pixel {miss_x}")
# proxy run: R2 of plot-type model within Asia with the bare except (as in handoff) vs common-sample scoring
dd = d.copy(); dd["lnP"] = np.log(dd.bio12); dd = dd.dropna(subset=["log_rs", "bio01", "lnP"])
u = dd[dd.continent == "Asia"].reset_index(drop=True)
res = {}
for nm, f in {"climate": "log_rs ~ bio01 + lnP", "climate+plot_type": "log_rs ~ bio01 + lnP + C(ptype)"}.items():
    p = np.full(len(u), np.nan)
    for tr, va in folds(u):
        try: p[va] = smf.ols(f, data=u.iloc[tr]).fit().predict(u.iloc[va])
        except Exception as e: print("  swallowed:", nm, type(e).__name__, str(e)[:100].replace("\n", " "))
    ok = np.isfinite(p); res[nm] = p
    print(f"PROXY within Asia {nm}: scored {ok.sum()}/{len(u)}  R2={r2_score(u.log_rs[ok], p[ok]):.3f}")
ok = np.isfinite(res["climate+plot_type"])
print(f"PROXY within Asia climate-only on the same {ok.sum()} sites: R2={r2_score(u.log_rs[ok], res['climate'][ok]):.3f}")
