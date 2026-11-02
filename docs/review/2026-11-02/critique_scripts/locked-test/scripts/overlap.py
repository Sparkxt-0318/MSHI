"""Overlap of v3 Europe test sites with the ORIGINAL v2 'Asia box' training table, and Asia-Europe proximity."""
import sys, json
import numpy as np, pandas as pd
from sklearn.neighbors import BallTree
W = sys.argv[1]; V2 = sys.argv[2]
R = 6371.0
def tree(df, la, lo): return BallTree(np.radians(df[[la, lo]].values), metric="haversine")
v2 = pd.read_parquet(V2)
out = {}
for tag in ["qc", "repo"]:
    s = pd.read_parquet(f"{W}/out/v3/sites_v3_{tag}.parquet")
    eu, asia = s[s.continent == "Europe"].reset_index(drop=True), s[s.continent == "Asia"].reset_index(drop=True)
    # 1) Europe test sites that coincide with a v2 Asia-box training site
    d, i = tree(v2, "latitude", "longitude").query(np.radians(eu[["lat", "lon"]].values), k=1)
    dk = d[:, 0] * R
    out[f"{tag}_europe_n"] = len(eu)
    out[f"{tag}_europe_east_of_25E"] = int((eu.lon >= 25).sum())
    for thr in [1, 5, 10]:
        out[f"{tag}_europe_sites_within_{thr}km_of_v2_asiabox_site"] = int((dk <= thr).sum())
    m = dk <= 5
    out[f"{tag}_europe_overlap_countries"] = eu.loc[m, "country"].value_counts().to_dict()
    # v2 sites (all 615) that lie within 5 km of a v3 Europe site
    d2, _ = tree(eu, "lat", "lon").query(np.radians(v2[["latitude", "longitude"]].values), k=1)
    out[f"{tag}_v2_asiabox_sites_within_5km_of_v3_europe_site"] = int((d2[:, 0] * R <= 5).sum())
    # 2) proximity of Europe test sites to nearest Asia TRAINING site
    d3, i3 = tree(asia, "lat", "lon").query(np.radians(eu[["lat", "lon"]].values), k=1)
    dk3 = d3[:, 0] * R
    out[f"{tag}_europe_to_nearest_asia_train_km"] = {"min": round(float(dk3.min()), 1), "q05": round(float(np.quantile(dk3, .05)), 1),
        "median": round(float(np.median(dk3)), 1), **{f"n_le_{t}km": int((dk3 <= t).sum()) for t in [25, 50, 100, 250, 500]}}
    close = eu.assign(dist=dk3, asia_country=asia.country.values[i3[:, 0]])[dk3 <= 250]
    out[f"{tag}_close_pairs_le250km"] = close[["country", "lat", "lon", "asia_country", "dist"]].round(2).sort_values("dist").values.tolist()[:15]
    # 3) Asia training sites in West Asia / Caucasus / Russia >= 60E / Kazakhstan
    wa = ["Turkey", "Cyprus", "Israel", "Iran", "Georgia", "Armenia", "Azerbaijan", "Lebanon", "Syria", "Jordan", "Iraq", "Saudi Arabia", "Kazakhstan", "Russia"]
    out[f"{tag}_asia_train_in_westasia_caucasus_russia_kaz"] = asia[asia.country.isin(wa)].country.value_counts().to_dict()
    out[f"{tag}_asia_train_n"] = len(asia)
print(json.dumps(out, indent=1, default=str))
