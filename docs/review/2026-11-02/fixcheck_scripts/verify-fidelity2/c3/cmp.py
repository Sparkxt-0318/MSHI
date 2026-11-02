"""Leaf-by-leaf comparison of two LockedTest result JSONs (verifier's own).
Groups: 'RF table' = selection_table / all_candidates_on_test rows with learner RF; 'selected-model' =
selected, primary, aoa (the selected model's leaves); 'other' = everything else.
Reports absolute and relative (|a-b| / max(|a|,|b|)) differences.  usage: cmp.py A.json B.json"""
import json, math, sys

A, B = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
SKIP = {"plan_sha256", "lock", "variant", "note", "vs_locked", "_provenance"}


def flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if not (p == "" and k in SKIP):
                yield from flat(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, o


def group(path):
    for tab in ("selection_table", "all_candidates_on_test"):
        if path.startswith(tab + "["):
            i = int(path[len(tab) + 1:path.index("]")])
            return "RF table" if A[tab][i]["learner"] == "RF" else "other table"
    if path.startswith(("selected", "primary", "aoa")):
        return f"selected-model ({A['selected']['learner']})"
    return "other"


fa, fb = dict(flat(A)), dict(flat(B))
assert set(fa) == set(fb), (set(fa) ^ set(fb))
rows = {}
for k in fa:
    x, y = fa[k], fb[k]
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x is None or y is None:
        same = x == y
        ad = rd = None
    else:
        same = x == y or (math.isnan(x) and math.isnan(y))
        ad = abs(x - y)
        rd = ad / max(abs(x), abs(y)) if max(abs(x), abs(y)) > 0 else 0.0
    g = rows.setdefault(group(k), {"n": 0, "diff": 0, "maxabs": 0.0, "maxrel": 0.0, "argabs": None, "argrel": None})
    g["n"] += 1
    if not same:
        g["diff"] += 1
        if ad is not None and ad > g["maxabs"]:
            g["maxabs"], g["argabs"] = ad, (k, x)
        if rd is not None and rd > g["maxrel"]:
            g["maxrel"], g["argrel"] = rd, (k, x)
print(f"{sys.argv[1].rsplit('/', 1)[-1]} vs {sys.argv[2].rsplit('/', 1)[-1]}: selected "
      f"{A['selected']['set']}/{A['selected']['learner']} vs {B['selected']['set']}/{B['selected']['learner']}")
for g, r in sorted(rows.items()):
    print(f"  {g:28} leaves {r['n']:4}  differ {r['diff']:3}  max abs {r['maxabs']:.3g} at {r['argabs']}  "
          f"max rel {r['maxrel']:.3g} at {r['argrel']}")
