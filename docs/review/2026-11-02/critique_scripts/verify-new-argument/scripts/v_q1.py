"""Exact replication of N2 Q1 (exp_plot_pixel.py L26-47) on the rebuilt v3 QC sites (no climate needed),
plus the IGBP codes under forest plots, by sample."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-new-argument/scripts")
from v_common import samp, LC, V


def igbp_group(c):  # verbatim L26-29
    c = np.asarray(c)
    return np.select([np.isin(c, [1, 2, 3, 4, 5]), np.isin(c, [8, 9]), np.isin(c, [10]), np.isin(c, [12, 14]), np.isin(c, [6, 7])],
                     ["Forest", "Savanna", "Grassland", "Agriculture", "Shrubland"], "Other")


d = pd.read_parquet(f"{V}/out/v3/sites_v3_qc.parquet")
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
                                 "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
                                 "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"})
d["ptype"] = np.where(d.ptype.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), d.ptype, "Other")
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d["pixel_code"] = np.where(inbox, samp(LC, d.lon.values, d.lat.values), np.nan)
d["pixel"] = np.where(d.pixel_code.isna() | (d.pixel_code == 0), "NA", igbp_group(d.pixel_code.fillna(0)))
s = d[d.pixel != "NA"]
R = {"Q1_n": int(len(s)), "Q1_crosstab_plot_x_pixel": pd.crosstab(s.ptype, s.pixel).to_dict(),
     "Q1_forest_share": dict(plot=round(float((s.ptype == "Forest").mean()), 3), pixel=round(float((s.pixel == "Forest").mean()), 3)),
     "Q1_agreement_forest_vs_not": round(float(((s.ptype == "Forest") == (s.pixel == "Forest")).mean()), 3),
     "Q1_plot_forest_pixel_nonforest": int(((s.ptype == "Forest") & (s.pixel != "Forest")).sum())}
H = json.load(open("/home/user/MSHI/docs/handoff/results/N2_plot_pixel.json"))
for k in R:
    print(k, "MATCH" if R[k] == H[k] else f"DIFF mine={R[k]} handoff={H[k]}")
print("outer keys:", sorted(R["Q1_crosstab_plot_x_pixel"].keys()), " inner keys:", sorted(next(iter(R["Q1_crosstab_plot_x_pixel"].values())).keys()))
print("plot classes in s:", s.ptype.value_counts().to_dict()); print("pixel classes in s:", s.pixel.value_counts().to_dict())
print("Q1 continent counts:", s.continent.value_counts().to_dict())
f = s[s.ptype == "Forest"]
print("forest plots in Q1:", len(f), " IGBP codes:", f.pixel_code.astype(int).value_counts().to_dict())
for nm, codes in [("1-5", [1, 2, 3, 4, 5]), ("1-5+8", [1, 2, 3, 4, 5, 8]), ("1-5+8+9", [1, 2, 3, 4, 5, 8, 9])]:
    print(f"Q1 sample: pixel-forest share at plots [{nm}] = {np.isin(s.pixel_code, codes).mean():.3f}; forest plots in such pixels = {np.isin(f.pixel_code, codes).mean():.3f}")
des = s[s.ptype == "Desert"]
print("Desert plots in Q1:", len(des), des.pixel_code.astype(int).value_counts().to_dict(), des.continent.value_counts().to_dict())
s.to_parquet(f"{V}/out/q1_sample.parquet")
