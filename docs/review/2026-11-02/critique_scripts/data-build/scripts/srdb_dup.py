import sys, pandas as pd, numpy as np
p = sys.argv[1]
d = pd.read_csv(p, low_memory=False)
d["row"] = d.index
s = d.dropna(subset=["Latitude","Longitude","Rs_annual"])
s = s[(s.Rs_annual>=50)&(s.Rs_annual<=4500)]
s = s[s.Manipulation.isin(["None","Control","control"]) | s.Manipulation.isna()].copy()
dup = s[s.Duplicate_record.notna()]
print("records with Duplicate_record:", len(dup))
rn = d.set_index("Record_number")
cols = ["Record_number","Study_number","Author","Duplicate_record","Site_name","Latitude","Longitude","Study_midyear","Rs_annual","Quality_flag","Manipulation"]
out = []
for _, x in dup.iterrows():
    tgt = x.Duplicate_record
    try: tgt = int(float(tgt))
    except: out.append((x.Record_number, tgt, "unparseable")); continue
    if tgt in rn.index:
        t = rn.loc[tgt]
        if isinstance(t, pd.DataFrame): t = t.iloc[0]
        in_repo = int(d.index[d.Record_number==tgt][0]) in s.index
        out.append((x.Record_number, tgt, t.Duplicate_record, in_repo, x.Study_number, t.Study_number, x.Rs_annual, t.Rs_annual, x.Study_midyear, t.Study_midyear, round(x.Latitude,3), round(t.Latitude,3)))
    else:
        out.append((x.Record_number, tgt, "target missing"))
o = pd.DataFrame(out, columns=["rec","dup_of","target_dup_field","target_in_repo_set","study","t_study","rs","t_rs","yr","t_yr","lat","t_lat"][:max(len(r) for r in out)])
pd.set_option("display.width", 250)
print(o.to_string())
print("\nTargets that themselves carry a Duplicate_record entry (symmetric):", o.target_dup_field.notna().sum() if "target_dup_field" in o else None)
print("Targets present in repo-filter set:", o.target_in_repo_set.sum())
# record numbers referenced by many
print(dup.Duplicate_record.value_counts().head())
# Q13 notes
q13 = s[s.Quality_flag.fillna("").str.contains("Q13")]
print("\nQ13 sample notes:")
for n in q13.Notes.dropna().head(15): print("  -", str(n)[:160])
print(q13.Study_number.value_counts().head(10))
