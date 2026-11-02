"""Leaf-by-leaf comparison of two clean-test result JSONs. usage: compare.py A.json B.json [labelA labelB]"""
import json, math, sys
A, B = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
la, lb = (sys.argv[3], sys.argv[4]) if len(sys.argv) > 4 else ("A", "B")
SKIP = {"plan_sha256", "lock", "variant", "note", "vs_locked", "_provenance"}


def flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if p == "" and k in SKIP:
                continue
            yield from flat(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, o


fa, fb = dict(flat(A)), dict(flat(B))
only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))


def is_rf(path, R):
    for tab in ("selection_table", "all_candidates_on_test"):
        if path.startswith(tab + "["):
            i = int(path[len(tab) + 1:path.index("]")])
            return R[tab][i]["learner"] == "RF"
    if path.startswith(("primary", "aoa")):
        return R["selected"]["learner"] == "RF"
    if path.startswith("selected."):
        return R["selected"]["learner"] == "RF"
    return False


diff = []
for k in sorted(set(fa) & set(fb)):
    x, y = fa[k], fb[k]
    same = (x == y) or (isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y))
    if not same:
        d = abs(x - y) if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) else None
        diff.append((k, x, y, d, is_rf(k, A)))
n = len(set(fa) & set(fb))
rf = [t for t in diff if t[4]]
nonrf = [t for t in diff if not t[4]]
print(f"{la} vs {lb}: selected {A['selected']['set']}/{A['selected']['learner']} vs {B['selected']['set']}/{B['selected']['learner']}; "
      f"{n} common leaves, {len(diff)} differ ({len(rf)} RF, {len(nonrf)} non-RF); only in {la}: {only_a}; only in {lb}: {only_b}")
if diff:
    print("  max |diff| RF:", max((t[3] for t in rf if t[3] is not None), default=None),
          " non-RF:", max((t[3] for t in nonrf if t[3] is not None), default=None))
for t in nonrf[:20]:
    print("  NON-RF DIFF", t[:4])
