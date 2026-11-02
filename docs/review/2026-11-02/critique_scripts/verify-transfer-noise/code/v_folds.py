import numpy as np, pandas as pd
V = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise"
def folds(df, seed=42, deg=5.0, k=5):   # exp_matrix.py:30-34
    b = (np.floor(df.lon / deg).astype(int).astype(str) + "_" + np.floor(df.lat / deg).astype(int).astype(str)).values
    u = np.unique(b); r = np.random.default_rng(seed); r.shuffle(u)
    for vb in np.array_split(u, min(k, len(u))):
        m = np.isin(b, vb); yield np.where(~m)[0], np.where(m)[0]
s = pd.read_parquet(f"{V}/data/v3/sites_v3_qc.parquet")
for c in ["Europe", "Asia", "North America"]:
    u = s[s.continent == c].reset_index(drop=True)
    for seed in (42, 43, 44):
        sz = [len(va) for _, va in folds(u, seed)]
        print(f"{c:14s} n={len(u)} seed {seed}: test-fold sizes {sz}")
# sensitivity: drop each Europe site in turn (v3 features drop 1 Europe site for missing C8) -> range of min/max fold sizes
u = s[s.continent == "Europe"].reset_index(drop=True)
mins, maxs = set(), set()
for seed in (42, 43):
    lo, hi = [], []
    for i in range(len(u)):
        sz = [len(va) for _, va in folds(u.drop(index=i).reset_index(drop=True), seed)]
        lo.append(min(sz)); hi.append(max(sz))
    print(f"Europe minus one site, seed {seed}: min fold size in [{min(lo)},{max(lo)}], max fold size in [{min(hi)},{max(hi)}]")
