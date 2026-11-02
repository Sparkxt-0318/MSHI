import json
H="/home/user/MSHI/docs/handoff/results/"
for L in ["OLS-TP","XGB"]:
    E=json.load(open(H+f"E6_matrix_{L}.json"))
    print(f"== {L}")
    for c in ["Asia","Europe","North America"]:
        w=E["within_cv"][c]; lo=E["loco"][c]
        print(f"  {c:14s} within r2 {w['r2']:+.3f} skill {w['skill']:+.3f} rmse {w['rmse']:.3f} | LOCO r2 {lo['r2']:+.3f} (penalty {w['r2']-lo['r2']:+.3f}) skill {lo['skill']:+.3f} rmse {lo['rmse']:.3f} (dRMSE {lo['rmse']-w['rmse']:+.3f})")
        for k,v in E["pairwise"].items():
            tr,te=k.split(" -> ")
            if te==c and tr in ["Asia","Europe","North America"]:
                print(f"      {k:28s} r2 {v['r2']:+.3f} penalty {w['r2']-v['r2']:+.3f} | rmse {v['rmse']:.3f} dRMSE {v['rmse']-w['rmse']:+.3f} | skill {v['skill']:+.3f}")
    # skill vs r2 sign disagreements
    dis=[(k,v['r2'],v['skill']) for k,v in E["pairwise"].items() if (v['r2']<0)!=(v['skill']<0)]
    print("  pairs where R2 and skill disagree in sign:", dis)
