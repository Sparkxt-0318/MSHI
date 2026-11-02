"""Checkpoint-1 diagnostic figure: site map + climate / ecosystem distributions of train vs test.
Also assigns each site to a country/continent with Natural Earth polygons (point-in-polygon).
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO, NE, SRDB, OUT = map(Path, sys.argv[1:5])
BLUE, ORANGE, INK, INK2, GRID, SURF = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
MOD = ["npp", "lst_day", "lst_night", "lst_diurnal_range"]
a = pd.read_parquet(REPO / "data/processed/training_features_v2.parquet").assign(set="Asia box (train)")
u = pd.read_parquet(REPO / "data/processed/us_validation_features_v2.parquet").assign(set="US box (test)")
d = pd.concat([a, u], ignore_index=True)
d["used_fnpp"] = d[MOD + ["log_rs_annual"]].notna().all(axis=1)
s = pd.read_csv(SRDB, low_memory=False)
isr = d.source == "srdb"
d.loc[isr, "ecosystem"] = s.loc[d.loc[isr, "site_id"].str.replace("srdb_", "").astype(int), "Ecosystem_type"].values
d["ecosystem"] = d["ecosystem"].fillna("COSORE site")

pts = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.longitude, d.latitude), crs=4326)
cty = gpd.read_file(NE / "ne_50m_admin_0_countries.geojson")[["ADMIN", "CONTINENT", "geometry"]]
j = gpd.sjoin(pts, cty, how="left", predicate="within")
j = j[~j.index.duplicated()]
# points off the 50 m coastline: nearest country within ~50 km
miss = j.CONTINENT.isna()
if miss.any():
    near = gpd.sjoin_nearest(pts[miss].to_crs(3857), cty.to_crs(3857), how="left", max_distance=50000)
    near = near[~near.index.duplicated()]
    j.loc[near.index, ["ADMIN", "CONTINENT"]] = near[["ADMIN", "CONTINENT"]].values
j["CONTINENT"] = j.CONTINENT.fillna("off-coast (>50 km from land)")
summ = {k: g.CONTINENT.value_counts().to_dict() for k, g in j.groupby("set")}
summ["countries_us_box"] = j[j.set.str.startswith("US")].ADMIN.fillna("NA").value_counts().to_dict()
summ["fnpp_used"] = j.groupby("set").used_fnpp.sum().astype(int).to_dict()
(OUT / "site_geography.json").write_text(json.dumps(summ, indent=1))
print(json.dumps(summ, indent=1))

plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF})
fig = plt.figure(figsize=(12, 8.2))
gs = fig.add_gridspec(3, 4, height_ratios=[1.35, 1, 1], hspace=0.75, wspace=0.35)
ax = fig.add_subplot(gs[0, :])
gpd.read_file(NE / "ne_110m_land.geojson").plot(ax=ax, color="#ecebe7", edgecolor="#cfcdc6", linewidth=0.4)
for setname, col in [("Asia box (train)", BLUE), ("US box (test)", ORANGE)]:
    g = d[d.set == setname]
    ax.scatter(g[g.used_fnpp].longitude, g[g.used_fnpp].latitude, s=12, c=col, edgecolors=SURF, linewidths=0.6,
               label=f"{setname}: used in F+NPP (n={int(g.used_fnpp.sum())})", zorder=3)
    ax.scatter(g[~g.used_fnpp].longitude, g[~g.used_fnpp].latitude, s=12, facecolors="none", edgecolors=col,
               linewidths=0.8, label=f"{setname}: dropped, MODIS missing (n={int((~g.used_fnpp).sum())})", zorder=3)
for x0, x1, y0, y1 in [(25, 180, -10, 80), (-125, -66, 24, 50)]:
    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color=INK2, lw=0.8, ls="--")
ax.set_xlim(-130, 182); ax.set_ylim(-15, 82); ax.set_aspect("equal")
ax.set_title("Sites by region (dashed = selection bounding boxes)", loc="left", color=INK, fontsize=10)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=7.5, frameon=False, ncol=2)
ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

panels = [("bio01", "Mean annual temp. (bio01, °C)"), ("bio12", "Annual precip. (bio12, mm)"),
          ("bio15", "Precip. seasonality (bio15, CV %)"), ("npp", "MODIS NPP (raw units)"),
          ("bio06", "Min temp. coldest month (bio06, °C)"), ("clay", "SoilGrids clay 5–15 cm"),
          ("log_rs_annual", "log Rs_annual (target)")]
for i, (col, lab) in enumerate(panels):
    axh = fig.add_subplot(gs[1 + i // 4, i % 4])
    v = d[col].dropna(); bins = np.linspace(v.quantile(.005), v.quantile(.995), 28)
    for setname, c in [("Asia box (train)", BLUE), ("US box (test)", ORANGE)]:
        axh.hist(d.loc[d.set == setname, col].dropna(), bins=bins, density=True, histtype="step", lw=2, color=c)
    axh.set_title(lab, loc="left", fontsize=8.5, color=INK); axh.set_yticks([])
    axh.grid(axis="x", color=GRID, lw=0.6)
axe = fig.add_subplot(gs[2, 3])
tab = pd.crosstab(d.ecosystem, d.set, normalize="columns").sort_values("Asia box (train)")
y = np.arange(len(tab)); h = 0.38
axe.barh(y - h / 2 - 0.02, tab["Asia box (train)"], height=h, color=BLUE)
axe.barh(y + h / 2 + 0.02, tab["US box (test)"], height=h, color=ORANGE)
axe.set_yticks(y); axe.set_yticklabels(tab.index, fontsize=7)
axe.set_title("SRDB ecosystem type (share)", loc="left", fontsize=8.5, color=INK)
fig.text(0.01, 0.005, "Histograms: density, step lines (blue = Asia box train, n=615; orange = US box test, n=274). "
         "Source: committed processed tables in Sparkxt-0318/MSHI + SRDB metadata.", fontsize=7, color=INK2)
fig.savefig(OUT / "checkpoint1_sites.png", dpi=170, bbox_inches="tight")
