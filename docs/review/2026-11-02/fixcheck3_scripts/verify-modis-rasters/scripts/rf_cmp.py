"""Leaf-by-leaf comparison of two LockedTest JSONs (verifier's own). Groups RF rows of selection_table /
all_candidates_on_test, other rows, the selected model's leaves (selected/primary/aoa), and the rest.
usage: rf_cmp.py A.json B.json"""
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
            return f"{tab}:" + ("RF" if A[tab][i]["learner"] == "RF" else "nonRF")
    if path.startswith(("selected", "primary", "aoa")):
        return f"selected-model({A['selected']['learner']})"
    return "other"
fa, fb = dict(flat(A)), dict(flat(B))
assert set(fa) == set(fb)
G = {}
for k in fa:
    x, y = fa[k], fb[k]
    g = G.setdefault(group(k), {"n": 0, "diff": 0, "maxabs": 0.0, "at": None, "over1e15": 0})
    g["n"] += 1
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        if x != y: g["diff"] += 1
        continue
    if x == y or (math.isnan(x) and math.isnan(y)):
        continue
    g["diff"] += 1
    ad = abs(x - y)
    if ad > 1e-15: g["over1e15"] += 1
    if ad > g["maxabs"]:
        g["maxabs"], g["at"] = ad, (k, x, y)
print(f"{sys.argv[1].rsplit('/',1)[-1]} vs {sys.argv[2].rsplit('/',1)[-1]}: selected "
      f"{A['selected']['set']}/{A['selected']['learner']} vs {B['selected']['set']}/{B['selected']['learner']}")
for g, r in sorted(G.items()):
    print(f"  {g:34} leaves {r['n']:4} differ {r['diff']:3} (>1e-15: {r['over1e15']:2}) max abs {r['maxabs']:.3g} at {r['at']}")
