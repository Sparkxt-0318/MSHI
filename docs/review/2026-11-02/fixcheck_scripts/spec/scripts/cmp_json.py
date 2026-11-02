import sys, json
def leaves(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from leaves(v, f"{p}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from leaves(v, f"{p}[{i}]")
    else:
        yield p, o
a = dict(leaves(json.load(open(sys.argv[1])))); b = dict(leaves(json.load(open(sys.argv[2]))))
# label selection_table / all_candidates entries by learner
A = json.load(open(sys.argv[1])); B = json.load(open(sys.argv[2]))
def lab(R, path):
    import re
    m = re.match(r"/(selection_table|all_candidates_on_test)\[(\d+)\]", path)
    if m:
        e = R[m.group(1)][int(m.group(2))]; return f"{e['learner']}/{e['set']}"
    return ""
only = set(a) ^ set(b)
diff = [(k, a[k], b[k]) for k in a if k in b and a[k] != b[k]]
print("keys only in one:", sorted(only))
print("n leaves", len(a), "n differing", len(diff))
learners = {}
for k, x, y in diff:
    l = lab(A, k) or k
    learners.setdefault(l.split("/")[0], []).append(abs(x - y) if isinstance(x, float) and isinstance(y, float) else (x, y))
for l, v in learners.items():
    nums = [d for d in v if isinstance(d, float)]
    print(f"  {l}: {len(v)} diffs, max abs {max(nums) if nums else None}, non-numeric {[d for d in v if not isinstance(d, float)][:3]}")
