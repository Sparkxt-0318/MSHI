"""Re-check guards-new-provenance-not-transitive: direct, reverse and features->clean_test scenarios, with the
real cosore_annual/build_sites stages in non-smoke sandboxes (raw inputs symlinked read-only, git stubbed)."""
import sys, json
sys.path.insert(0, "fixcheck3_scripts/chain/scripts")
import cc
from cc import full_sand, reset, link_raw, stub_git, seed_committed, statuses, summary, rows, SCR
import logging
logging.basicConfig(level=logging.WARNING)
stub_git()
from mshi.run import run
from mshi.io import result_staleness, read_json
mode = sys.argv[1]
base = SCR / "work" / f"c05_{mode}"
reset(base)

def show(tag, sand, code=None):
    s = summary(sand)
    print(f"--- {tag}: exit={code} summary={s}")
    for k, v in statuses(sand).items():
        pass
    for p in sorted(sand.path("results").glob("*.json")):
        if p.name.startswith("reproduction"):
            continue
        print(f"    staleness {p.name}: {result_staleness(sand, read_json(p))}")

A = lambda d: None
if mode == "direct":
    B = lambda d: d["cosore_annual"].__setitem__("rs_range", [50.0, 1000.0])
    a = full_sand("s", A, base); link_raw(a); seed_committed(a)       # committed state under config A
    b = full_sand("s", B, base)
    n0 = len(cc.runlog(b))
    code = run(["build_sites", "repro_checks"], b)
    print("run log:", json.dumps(statuses(b, n0), indent=0)[:900])
    show("config B, build_sites+repro_checks on A's cosore_annual", b, code)
    print("rows (first 3):", [(r["quantity"], r["status"], r["note"][:90]) for r in rows(b)[:3]])
elif mode == "reverse":
    C = lambda d: d["cosore_annual"].__setitem__("molar_mass_c", 12.0)
    a = full_sand("s", A, base); link_raw(a); seed_committed(a)
    c = full_sand("s", C, base)
    code1 = run(["build_sites", "repro_checks"], c)
    print("step1 statuses:", {k: v[:110] for k, v in statuses(c).items()})
    show("step 1 (C: build_sites, repro_checks)", c, code1)
    n = len(cc.runlog(c))
    code2 = run(["cosore_annual", "repro_checks"], c)
    print("step2 statuses:", {k: v[:110] for k, v in statuses(c, n).items()})
    show("step 2 (C: cosore_annual, repro_checks)", c, code2)
    print("rows STALE notes:", sorted({r["note"][:100] for r in rows(c) if r["status"] == "STALE"}))
    n = len(cc.runlog(c))
    code3 = run(["build_sites", "repro_checks"], c)
    print("step3 statuses:", {k: v[:110] for k, v in statuses(c, n).items()})
    show("step 3 (C: build_sites, repro_checks)", c, code3)
elif mode == "features":
    # config C, committed build under A, then features under C; then clean_test under C with A's features.json
    import numpy as np, pandas as pd
    from mshi.io import write_result, write_table
    C = lambda d: d["cosore_annual"].__setitem__("molar_mass_c", 12.0)
    a = full_sand("s", A, base); link_raw(a); seed_committed(a)
    # A's features.json recording two (synthetic) feature tables
    outs = []
    for t in ("qc", "repo"):
        st = pd.read_parquet(a.path("derived", f"sites_v3_{t}.parquet"))
        outs.append(write_table(st.assign(bio01=1.0), a.path("interim", f"features_v3_{t}.parquet")))
    write_result(a, {"synthetic": True}, "features.json", outputs=outs)
    c = full_sand("s", C, base)
    code = run(["features"], c)
    print("features under C:", code, statuses(c))
    n = len(cc.runlog(c))
    code = run(["clean_test"], c)
    print("clean_test under C:", code, {k: v[:200] for k, v in statuses(c, n).items()})
