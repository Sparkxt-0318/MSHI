"""Distribution of |old - head| over differing RF-table leaves (selection_table / all_candidates_on_test rows
with learner RF), per old run. usage: rf_dist.py HEAD.json OLD1.json [OLD2.json ...]"""
import json, math, sys
import numpy as np
H = json.load(open(sys.argv[1]))
def rf_leaves(o):
    out = {}
    for tab in ("selection_table", "all_candidates_on_test"):
        for i, row in enumerate(o[tab]):
            if row["learner"] != "RF":
                continue
            def walk(x, p):
                if isinstance(x, dict):
                    for k, v in x.items(): walk(v, f"{p}.{k}")
                elif isinstance(x, list):
                    for j, v in enumerate(x): walk(v, f"{p}[{j}]")
                elif isinstance(x, (int, float)) and not isinstance(x, bool):
                    out[p] = x
            walk(row, f"{tab}[{i}]")
    return out
h = rf_leaves(H)
for f in sys.argv[2:]:
    o = rf_leaves(json.load(open(f)))
    d = np.array([abs(o[k] - h[k]) for k in h if o[k] != h[k] and not (math.isnan(o[k]) and math.isnan(h[k]))])
    ulps = np.array([abs(o[k] - h[k]) / np.spacing(abs(h[k])) for k in h if o[k] != h[k]])
    print(f"{f.rsplit('/',1)[-1]}: RF-table numeric leaves {len(h)}, differ {len(d)}, median {np.median(d):.2e}, "
          f"max {d.max():.2e}, n>5e-16 {(d > 5e-16).sum()}, n>1e-15 {(d > 1e-15).sum()}, max ulps {ulps.max():.0f}")
