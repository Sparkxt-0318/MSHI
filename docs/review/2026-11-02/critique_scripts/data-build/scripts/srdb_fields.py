import sys, pandas as pd, numpy as np
p = sys.argv[1]
raw = pd.read_csv(p, low_memory=False, keep_default_na=False, dtype=str)
print("rows", len(raw)); print(list(raw.columns))
d = pd.read_csv(p, low_memory=False)
print("pandas", pd.__version__)
# Manipulation raw strings in rows passing lat/lon/rs and Rs range
m = d.dropna(subset=["Latitude","Longitude","Rs_annual"])
m = m[(m.Rs_annual>=50)&(m.Rs_annual<=4500)]
idx = m.index
print("rows with coords+Rs in range:", len(idx))
vc = raw.loc[idx, "Manipulation"].value_counts()
print("n distinct Manipulation raw strings:", len(vc))
print(vc.head(60).to_string())
# which raw strings pandas converts to NaN
print("\nraw strings that pandas reads as NaN:", raw.loc[idx][d.loc[idx,"Manipulation"].isna()]["Manipulation"].value_counts().to_dict())
kept = d.loc[idx][d.loc[idx,"Manipulation"].isin(["None","Control","control"]) | d.loc[idx,"Manipulation"].isna()]
print("kept by v3 filter:", len(kept))
print("kept raw strings:", raw.loc[kept.index,"Manipulation"].value_counts().to_dict())
# candidate control-like spellings not kept
nk = raw.loc[idx.difference(kept.index),"Manipulation"]
import re
pat = re.compile(r"(^none|control|ambient|^no |^unmanip|^natural|^undisturbed|^untreated|^ck$|reference|^intact|^na$|^n/a|^-$)", re.I)
cand = nk[nk.str.strip().str.contains(pat)]
print("\nNOT-kept strings that look like controls/no-treatment:")
print(cand.value_counts().to_string())
