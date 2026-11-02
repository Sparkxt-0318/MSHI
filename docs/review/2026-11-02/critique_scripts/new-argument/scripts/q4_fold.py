import sys, numpy as np, pandas as pd, statsmodels.formula.api as smf
d = pd.read_parquet(sys.argv[1]).dropna(subset=["log_rs", "bio01", "lnP"])
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
    "Open shrubland": "Shrubland", "Cropland": "Agriculture", "Savannas": "Savanna"})
def folds(df, seed=42, deg=5.0, k=5):   # exp_plot_pixel.py L60-64 verbatim
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        mm = np.isin(b, vb); yield np.where(~mm)[0], np.where(mm)[0]
u = d[d.continent == "Asia"].reset_index(drop=True)
for i, (tr, va) in enumerate(folds(u)):
    try:
        smf.ols("log_rs ~ bio01 + lnP + C(ptype)", data=u.iloc[tr]).fit().predict(u.iloc[va])
    except Exception as e:
        print(f"fold {i}: n_val={len(va)} classes only in validation: {sorted(set(u.ptype.iloc[va]) - set(u.ptype.iloc[tr]))}; error: {type(e).__name__}: {str(e)[:120]}")
