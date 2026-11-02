"""Replicate exp_plot_pixel.py Q1 (no WorldClim needed) and exp_forest_bias.py sample (minus WorldClim dropna)
on the rebuilt v3 QC sites with the committed land-cover raster. Read-only on inputs."""
import json, sys
import numpy as np, pandas as pd, rasterio
SITES, LC = sys.argv[1], sys.argv[2]

def samp(path, lon, lat):
    with rasterio.open(path) as s:
        return np.array([x[0] for x in s.sample(list(zip(lon, lat)))], float)

def igbp_group(c):  # verbatim from exp_plot_pixel.py L26-29
    c = np.asarray(c)
    return np.select([np.isin(c, [1, 2, 3, 4, 5]), np.isin(c, [8, 9]), np.isin(c, [10]), np.isin(c, [12, 14]), np.isin(c, [6, 7])],
                     ["Forest", "Savanna", "Grassland", "Agriculture", "Shrubland"], "Other")

d = pd.read_parquet(SITES)
# exp_plot_pixel.py L33-36 verbatim
d["ptype"] = d.ecosystem.replace({"Evergreen needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
                                 "Mixed forests": "Forest", "Deciduous needleleaf forest": "Forest", "Open shrubland": "Shrubland",
                                 "Closed shrubland": "Shrubland", "Woody savanna": "Savanna", "Croplands": "Agriculture", "Cropland": "Agriculture", "Savannas": "Savanna"})
d["ptype"] = np.where(d.ptype.isin(["Forest", "Grassland", "Agriculture", "Shrubland", "Savanna", "Desert"]), d.ptype, "Other")
inbox = (d.lon.between(25, 180) & d.lat.between(-10, 80)) | (d.lon.between(-125, -66) & d.lat.between(24, 50))
d["pixel_code"] = np.where(inbox, samp(LC, d.lon.values, d.lat.values), np.nan)
d["pixel"] = np.where(d.pixel_code.isna() | (d.pixel_code == 0), "NA", igbp_group(d.pixel_code.fillna(0)))
s = d[d.pixel != "NA"]
print("ecosystem values (all 971 QC sites):"); print(d.ecosystem.value_counts(dropna=False).to_string())
print("\nQ1_n", len(s))
ct = pd.crosstab(s.ptype, s.pixel)
print("crosstab rows=plot(ptype), cols=pixel:\n", ct.to_string())
print("\nto_dict() outer keys (what the JSON shows):", list(ct.to_dict().keys()))
print("forest share plot/pixel:", round((s.ptype == "Forest").mean(), 3), round((s.pixel == "Forest").mean(), 3))
print("agreement:", round(((s.ptype == "Forest") == (s.pixel == "Forest")).mean(), 3), "plotF_pixNF:", int(((s.ptype == "Forest") & (s.pixel != "Forest")).sum()))
print("continents in Q1 sample:", s.continent.value_counts().to_dict())
# raw IGBP codes at forest plots
print("\nIGBP code at plots, by plot type (rows=ptype):")
print(pd.crosstab(s.ptype, s.pixel_code.astype(int)).to_string())
s.to_parquet(sys.argv[3])
