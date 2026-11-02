import sys, numpy as np, pandas as pd
SRDB, CI, W = sys.argv[1:4]
s = pd.read_csv(SRDB, low_memory=False)
df = s.rename(columns={"Latitude":"latitude","Longitude":"longitude","Rs_annual":"rs_annual","Manipulation":"manipulation"})
df = df.dropna(subset=["latitude","longitude","rs_annual"]); df = df[(df.rs_annual>=50)&(df.rs_annual<=4500)]
df = df[df.manipulation.isin(["None","Control","control",None]) | df.manipulation.isna()].copy()
df["row"] = df.index; df["source"]="srdb"
df["cell"] = list(zip((df.longitude/0.05).round().astype(int), (df.latitude/0.05).round().astype(int)))
cells = df.groupby("cell").row.agg(["min","size"])
orig = pd.concat([pd.read_parquet(f"{CI}/training_features_v2.parquet"), pd.read_parquet(f"{CI}/us_validation_features_v2.parquet")])
o = orig[orig.source=="srdb"].copy(); o["row"] = o.site_id.str.replace("srdb_","").astype(int)
o = o.merge(df[["row","cell"]], on="row", how="left")
print("original Asia-box+US-box SRDB sites:", len(o), "matched to repo-filter rows:", o.cell.notna().sum())
o = o.join(cells, on="cell")
multi = o[o["size"]>1]
print("sites whose 0.05-deg cell had >1 eligible SRDB record:", len(multi))
print("  kept record == lowest row in cell:", int((multi.row==multi["min"]).sum()), " != lowest:", int((multi.row!=multi["min"]).sum()))
# what does the original code actually do? replicate deduplicate_spatial on SRDB(+COSORE) and compare
c = pd.read_csv(f"{W}/data/cosore_annual.csv")[["site_id","source","longitude","latitude","rs_annual"]]
c = c[(c.rs_annual>=50)&(c.rs_annual<=4500)]
x = df.assign(site_id="srdb_"+df.row.astype(str))[["site_id","source","longitude","latitude","rs_annual"]]
allp = pd.concat([x, c], ignore_index=True).sort_values("source", ascending=True).reset_index(drop=True)
gl = (allp.longitude/0.05).round().astype(int); gt=(allp.latitude/0.05).round().astype(int)
allp["__cell"] = list(zip(gl,gt)); kept = allp.drop_duplicates(subset="__cell", keep="first")
ks = set(kept.site_id); osid = set(orig.site_id)
print("replicated original dedup: kept", len(kept), "; original Asia+US site_ids reproduced:", len(osid & ks), "of", len(osid))
