"""Compare prototype and port MODIS point tables. usage: compare.py A.parquet B.parquet"""
import sys
import numpy as np, pandas as pd
a, b = pd.read_parquet(sys.argv[1]), pd.read_parquet(sys.argv[2])
print("columns A", list(a.columns), "| B", list(b.columns))
print("dtypes equal:", dict(a.dtypes) == dict(b.dtypes), "| site_key order equal:", list(a.site_key) == list(b.site_key))
b = b.set_index("site_key").loc[a.site_key].reset_index()
for c in ["npp", "lst_day", "lst_night"]:
    x, y = a[c].to_numpy(), b[c].to_numpy()
    nan_same = (np.isnan(x) == np.isnan(y)).all()
    f = ~np.isnan(x) & ~np.isnan(y)
    exact = int((x[f] == y[f]).sum())
    d = np.abs(x[f] - y[f])
    rel = d / np.abs(x[f]).clip(1e-300)
    print(f"{c:9s}: NaN pattern same {nan_same} (NaN {int(np.isnan(x).sum())}); finite {int(f.sum())}, bit-identical {exact}, "
          f"max|diff| {d.max() if d.size else 0:.3g}, max rel {rel.max() if rel.size else 0:.3g}; "
          f"n equal {bool((a[c + '_n'] == b[c + '_n']).all())} (n range {a[c + '_n'].min()}-{a[c + '_n'].max()})")
