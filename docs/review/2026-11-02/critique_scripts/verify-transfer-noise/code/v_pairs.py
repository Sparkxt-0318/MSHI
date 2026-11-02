import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique/verify-transfer-noise/code")
from v_common import load
B = 1000

def site_pairs(r, fn):
    """fn(rec_i, rec_j) -> category or None. Returns DataFrame of per-site sums and counts per category."""
    rows = []
    for s, g in r.groupby("site"):
        if len(g) < 2: continue
        v = g.to_dict("records")
        acc = {}
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                h = 0.5 * (v[i]["log_rs"] - v[j]["log_rs"]) ** 2
                for c in fn(v[i], v[j]):
                    a = acc.setdefault(c, [0.0, 0]); a[0] += h; a[1] += 1
        for c, (sm, n) in acc.items(): rows.append((s, c, sm, n))
    return pd.DataFrame(rows, columns=["site", "cat", "sum", "n"])

def cluster_boot(P, cats, seed=0):
    sites = P.site.unique(); rng = np.random.default_rng(seed)
    S = P.pivot_table(index="site", columns="cat", values="sum", fill_value=0).reindex(sites, fill_value=0)
    N = P.pivot_table(index="site", columns="cat", values="n", fill_value=0).reindex(sites, fill_value=0)
    out = {c: [] for c in cats}
    for _ in range(B):
        idx = rng.integers(0, len(sites), len(sites))
        s, n = S.values[idx].sum(0), N.values[idx].sum(0)
        m = dict(zip(S.columns, s / np.where(n > 0, n, np.nan)))
        for c in cats:
            out[c].append(m[c[0]] - m[c[1]] if isinstance(c, tuple) else m[c])
    return {c: (round(float(np.nanquantile(v, .025)), 4), round(float(np.nanquantile(v, .975)), 4)) for c, v in out.items()}

# ---------- N3 (SRDB-only QC records) ----------
r = load("qc", srdb_only=True)
def n3(a, b):
    c = []
    same_study = a["S_Study_number"] == b["S_Study_number"]
    if same_study:
        c.append("same_study"); c.append("same_study_same_year" if a["S_Study_midyear"] == b["S_Study_midyear"] else "same_study_diff_year")
    else:
        c.append("diff_study")
        if a["S_Study_midyear"] == b["S_Study_midyear"]: c.append("diff_study_same_year")
        if a["S_Meas_method"] == b["S_Meas_method"]: c.append("diff_study_same_method")
        if a["S_Study_midyear"] == b["S_Study_midyear"] and a["S_Meas_method"] == b["S_Meas_method"] and a["S_Ecosystem_type"] == b["S_Ecosystem_type"]:
            c.append("diff_study_same_year_same_method_same_ecosystem")
    return c
P = site_pairs(r, n3)
tot = P.groupby("cat").agg(n=("n", "sum"), s=("sum", "sum"), sites=("site", "nunique"))
tot["semivar"] = tot.s / tot.n
print(tot[["n", "sites", "semivar"]].round(4).to_string())
for c in ["diff_study", "same_study", "diff_study_same_year_same_method_same_ecosystem"]:
    q = P[P.cat == c].sort_values("n", ascending=False)
    print(f"{c}: top1 share {q.n.iloc[0]/q.n.sum():.3f}, top3 {q.n.iloc[:3].sum()/q.n.sum():.3f}, top10 {q.n.iloc[:10].sum()/q.n.sum():.3f}, n_sites {len(q)}")
ci = cluster_boot(P, ["diff_study", "same_study", ("diff_study", "same_study"), "diff_study_same_year_same_method_same_ecosystem"])
print("site-cluster bootstrap CIs:", ci)
# site-weighted means and within-site paired comparison
W = P.assign(m=P["sum"] / P.n).pivot_table(index="site", columns="cat", values="m")
print("site-weighted mean semivar: diff", round(W.diff_study.mean(), 4), " same", round(W.same_study.mean(), 4))
both = W.dropna(subset=["diff_study", "same_study"])
print("sites with both:", len(both), " share diff>same:", round(float((both.diff_study > both.same_study).mean()), 3),
      " median ratio:", round(float((both.diff_study / both.same_study).median()), 3))

# ---------- E1 (all QC records, incl. COSORE; pairs need Study_midyear) ----------
r1 = load("qc")
n_i = r1.groupby("site").size()
pairs_tot = (n_i * (n_i - 1) / 2)
pm = pairs_tot[n_i >= 2].sort_values(ascending=False)
print("E1 multi-record sites:", len(pm), " total within-site pairs:", int(pm.sum()), " top10 share:", round(pm.iloc[:10].sum() / pm.sum(), 3))
y1 = r1.dropna(subset=["S_Study_midyear"])
y1 = y1[y1.site.map(n_i) >= 2]
def e1(a, b):
    return ["same_year" if a["S_Study_midyear"] == b["S_Study_midyear"] else "diff_year"]
P1 = site_pairs(y1, e1)
t1 = P1.groupby("cat").agg(n=("n", "sum"), s=("sum", "sum")); t1["semivar"] = t1.s / t1.n
print(t1.round(4).to_string())
q = P1[P1.cat == "diff_year"].sort_values("n", ascending=False)
print("diff_year top5 share:", round(q.n.iloc[:5].sum() / q.n.sum(), 3))
print("site-cluster CIs:", cluster_boot(P1, ["same_year", "diff_year", ("diff_year", "same_year")]))
