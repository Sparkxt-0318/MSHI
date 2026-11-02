"""Patch the prototype's hard-coded sizes (only these 5 literals) for a reduced but identical comparison."""
import sys
src = open(sys.argv[1]).read()
reps = [("XGBP = dict(n_estimators=250,", "XGBP = dict(n_estimators=40,"),
        ("RandomForestRegressor(500,", "RandomForestRegressor(40,"),
        ("deg=None, n=2000, seed=42)", "deg=None, n=300, seed=42)"),
        ("    for _ in range(2000):\n        bi, bo", "    for _ in range(300):\n        bi, bo"),
        ("for s in range(20)]", "for s in range(4)]")]
for a, b in reps:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
open(sys.argv[2], "w").write(src)
print("ok")
