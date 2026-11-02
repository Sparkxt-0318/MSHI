import sys
import numpy as np, pandas as pd
sys.path.insert(0, f"/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/code")
from v_common import cluster, V
CI = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed"
# (1) original dedup replication (legacy/src/build_target.py:149-161) on repo-filter SRDB + COSORE
s = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
df = s.rename(columns={"Latitude": "latitude", "Longitude": "longitude", "Rs_annual": "rs_annual"})
df = df.dropna(subset=["latitude", "longitude", "rs_annual"]); df = df[(df.rs_annual >= 50) & (df.rs_annual <= 4500)]
df = df[df.Manipulation.isin(["None", "Control", "control"]) | df.Manipulation.isna()].copy()
print("repo-filter SRDB records:", len(df))
df["site_id"] = "srdb_" + df.index.astype(str); df["source"] = "srdb"
c = pd.read_csv(f"{V}/data/cosore/cosore_annual.csv")[["site_id", "source", "longitude", "latitude", "rs_annual"]]
allp = pd.concat([df[["site_id", "source", "longitude", "latitude", "rs_annual"]], c], ignore_index=True)
allp = allp.sort_values("source", ascending=True).reset_index(drop=True)
allp["__cell"] = list(zip((allp.longitude / 0.05).round().astype(int), (allp.latitude / 0.05).round().astype(int)))
kept = allp.drop_duplicates(subset="__cell", keep="first")
orig = pd.concat([pd.read_parquet(f"{CI}/training_features_v2.parquet"), pd.read_parquet(f"{CI}/us_validation_features_v2.parquet")])
print("replicated dedup kept:", len(kept), " original site_ids reproduced:", len(set(orig.site_id) & set(kept.site_id)), "of", len(orig))
# lowest-row check among multi-record cells, for original SRDB sites
df["cell"] = list(zip((df.longitude / 0.05).round().astype(int), (df.latitude / 0.05).round().astype(int)))
df["row"] = df.index
cells = df.groupby("cell").row.agg(["min", "size"])
o = orig[orig.source == "srdb"].copy(); o["row"] = o.site_id.str.replace("srdb_", "").astype(int)
o = o.merge(df[["row", "cell"]], on="row", how="left").join(cells, on="cell")
m = o[o["size"] > 1]
print("original SRDB sites in cells with >1 eligible SRDB record:", len(m), " kept==lowest row:", int((m.row == m["min"]).sum()))
# (2) E4 site units: 5-km clusters of v3 base records (exp_ablation.py:40-53) vs 0.05-deg cells of the same records
r = pd.read_parquet(f"{V}/data/v3/records_v3.parquet")
r = r[~r.f_offland & ~r.f_coord].reset_index(drop=True)
r["site"] = cluster(r)
st = r.groupby("site").agg(lat=("lat", "mean"), lon=("lon", "mean"), country=("geo_country", lambda x: x.mode().iat[0]))
ba = st.lon.between(25, 180) & st.lat.between(-10, 80); bu = st.lon.between(-125, -66) & st.lat.between(24, 50)
print("E4 clusters in Asia box:", int(ba.sum()), " in US box:", int(bu.sum()))
rr = r.assign(src_o=np.where(r.src == "cosore", "cosore", "srdb")).sort_values("src_o", kind="stable").reset_index(drop=True)
rr["__cell"] = list(zip((rr.lon / 0.05).round().astype(int), (rr.lat / 0.05).round().astype(int)))
kc = rr.drop_duplicates(subset="__cell", keep="first")
print("same records, 0.05-deg cells in Asia box:", int((kc.lon.between(25, 180) & kc.lat.between(-10, 80)).sum()),
      " in US box:", int((kc.lon.between(-125, -66) & kc.lat.between(24, 50)).sum()))
print("US-box clusters by country:", st[bu].country.value_counts().to_dict())
