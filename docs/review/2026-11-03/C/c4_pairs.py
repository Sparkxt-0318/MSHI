"""Check 4: recompute the pair statistic (N3, redone) by brute force over the real records for Europe, South America
and Africa, and compare with results/noise_ceiling.json (estimates, pair counts, sites, max site share).
Also: the same pairs restricted to SRDB records only (N3's choice) to show what the COSORE change does."""
import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/p2review/C")
import json
import numpy as np
from common import REPO, load_real

res = json.load(open(f"{REPO}/results/noise_ceiling.json"))
r, s = load_real()
for cont in ["Europe", "South America", "Africa", "Oceania"]:
    d = r[r.cont == cont]
    same, diff, per_site_same, per_site_diff = [], [], {}, {}
    same_srdb, diff_srdb = [], []
    for sid, g in d.groupby("site"):
        v, st, src = g.log_rs.to_numpy(), g.study.to_numpy(), g.src.to_numpy()
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                h = 0.5 * (v[i] - v[j]) ** 2
                if st[i] == st[j]:
                    same.append(h); per_site_same[sid] = per_site_same.get(sid, 0) + 1
                else:
                    diff.append(h); per_site_diff[sid] = per_site_diff.get(sid, 0) + 1
                if src[i] == "srdb" and src[j] == "srdb":
                    (same_srdb if st[i] == st[j] else diff_srdb).append(h)
    p = res["groups"][cont]["pairs"]
    print(f"== {cont}")
    print(f"  same : brute {np.mean(same):.12f} n {len(same)} sites {len(per_site_same)} maxshare "
          f"{max(per_site_same.values())/len(same):.6f} | stage {p['same_study']['semivariance']['estimate']:.12f} "
          f"n {p['same_study']['n_pairs']} sites {p['same_study']['n_sites']} maxshare {p['same_study']['max_site_share']:.6f}")
    print(f"  diff : brute {np.mean(diff):.12f} n {len(diff)} sites {len(per_site_diff)} maxshare "
          f"{max(per_site_diff.values())/len(diff):.6f} | stage {p['diff_study']['semivariance']['estimate']:.12f} "
          f"n {p['diff_study']['n_pairs']} sites {p['diff_study']['n_sites']} maxshare {p['diff_study']['max_site_share']:.6f}")
    print(f"  diff-same brute {np.mean(diff)-np.mean(same):.12f} stage {p['diff_minus_same']['estimate']:.12f}")
    print(f"  SRDB-only pairs (N3): same {np.mean(same_srdb):.4f} (n {len(same_srdb)}), diff "
          f"{np.mean(diff_srdb) if diff_srdb else float('nan'):.4f} (n {len(diff_srdb)})")
