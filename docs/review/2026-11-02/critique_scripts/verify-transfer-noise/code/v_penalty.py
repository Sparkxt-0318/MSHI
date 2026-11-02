import json, sys, math
H = "/home/user/MSHI/docs/handoff/results"
for L in ["OLS-TP", "XGB"]:
    R = json.load(open(f"{H}/E6_matrix_{L}.json"))
    W, LO, P = R["within_cv"], R["loco"], R["pairwise"]
    print(f"===== {L}")
    for te in W:
        w = W[te]
        print(f"[{te}] within r2={w['r2']} rmse={w['rmse']} skill={w['skill']} | LOCO r2={LO[te]['r2']} pen={w['r2']-LO[te]['r2']:+.3f} dRMSE={LO[te]['rmse']-w['rmse']:+.3f}")
        for k, v in P.items():
            src, dst = k.split(" -> ")
            if dst == te:
                print(f"     {k:32s} r2={v['r2']:+.3f} penR2={w['r2']-v['r2']:+.3f}  dRMSE={v['rmse']-w['rmse']:+.3f} ({100*(v['rmse']-w['rmse'])/w['rmse']:+.1f}%)  skill={v['skill']:+.3f}")
    # sign disagreements r2 vs skill
    allv = list(P.items()) + [("LOCO "+k, v) for k, v in LO.items()] + [("WITHIN "+k, v) for k, v in W.items()]
    dis = [(k, v["r2"], v["skill"]) for k, v in allv if (v["r2"] < 0) != (v["skill"] < 0)]
    print("sign disagreements:", dis)
    # target-mean skill = 1 - sqrt(1 - r2)
    for k in ["North America -> Europe", "Asia -> Europe"]:
        print(k, "target-mean skill", round(1 - math.sqrt(1 - P[k]['r2']), 4), "vs training-mean skill", P[k]['skill'])
    print("Europe within target-mean skill", round(1 - math.sqrt(1 - W['Europe']['r2']), 4), "vs", W['Europe']['skill'])
