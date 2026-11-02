"""Finding 09, North America: Q4 R2 for the three models on the handoff's samples vs a common in-box sample (PROXY climate)."""
import sys, numpy as np, pandas as pd, statsmodels.formula.api as smf
from sklearn.metrics import r2_score
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import V
q1 = pd.read_parquet(f"{V}/out/q1_sample.parquet")[["site_id", "pixel"]]
d = pd.read_parquet(f"{V}/out/sites_qc_proxy.parquet")
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
                                 "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
                                 "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"})
d["ptype"] = np.where(d.ptype.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), d.ptype, "Other")
d = d.merge(q1, on="site_id", how="left"); d["pixel"] = d.pixel.fillna("NA")
d["lnP"] = np.log(d.bio12); d = d.dropna(subset=["log_rs", "bio01", "lnP"])
s = d[d.pixel != "NA"]
def folds(df, seed=42, deg=5.0, k=5):
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, k):
        mm = np.isin(b, vb); yield np.where(~mm)[0], np.where(mm)[0]
forms = {"climate": "log_rs ~ bio01 + lnP", "climate+plot_type": "log_rs ~ bio01 + lnP + C(ptype)", "climate+pixel_type": "log_rs ~ bio01 + lnP + C(pixel)"}
for cont in ["Asia", "North America"]:
    for samp_name, base in [("handoff samples (pixel: in-box s; others: all d)", None), ("common in-box s", s)]:
        out = []
        for name, f in forms.items():
            data = base if base is not None else (s if "pixel" in name else d)
            u = data[data.continent == cont].reset_index(drop=True); p = np.full(len(u), np.nan)
            for tr, va in folds(u):
                try: p[va] = smf.ols(f, data=u.iloc[tr]).fit().predict(u.iloc[va])
                except Exception: pass
            ok = np.isfinite(p); out.append(f"{name}: {r2_score(u.log_rs[ok], p[ok]):.3f} ({ok.sum()}/{len(u)})")
        print(cont, "|", samp_name, "|", "; ".join(out))
