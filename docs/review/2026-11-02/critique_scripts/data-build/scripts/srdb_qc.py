import sys, pandas as pd, numpy as np
p = sys.argv[1]
raw = pd.read_csv(p, low_memory=False, keep_default_na=False, dtype=str)
s = pd.read_csv(p, low_memory=False)
s = s.dropna(subset=["Latitude","Longitude","Rs_annual"])
s = s[(s.Rs_annual>=50)&(s.Rs_annual<=4500)]
s = s[s.Manipulation.isin(["None","Control","control"]) | s.Manipulation.isna()].copy()
print("repo-filter records", len(s))
for col in ["Meas_method","Quality_flag","Ecosystem_type","Ecosystem_state"]:
    print("\n==", col, "(raw strings)"); print(raw.loc[s.index, col].value_counts().to_string())
print("\n== Annual_coverage")
ac = s.Annual_coverage
print(ac.describe()); print("NaN:", ac.isna().sum(), " >1:", (ac>1).sum(), " <0.5:", (ac<0.5).sum(), " ==0:", (ac==0).sum())
print(raw.loc[s.index,"Annual_coverage"][s.Annual_coverage.isna()].value_counts().head())
print("values >1:", ac[ac>1].value_counts().sort_index().to_dict())
print("\n== Duplicate_record (raw)"); print(raw.loc[s.index,"Duplicate_record"].value_counts().head(20).to_string())
print("non-NA Duplicate_record:", s.Duplicate_record.notna().sum())
