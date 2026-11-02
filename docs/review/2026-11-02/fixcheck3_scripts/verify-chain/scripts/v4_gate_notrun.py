"""Claim 4: the reproduction gate treats NOT RUN as passing, so a producer that fails in the invocation turns
the FAIL rows of a current, non-reproducing build into NOT RUN and opens the gate.
Config B (site_build.merge_radius_km 20) gives a current build that does not reproduce. Two triggers:
 (a) build_sites errors (SRDB file fails its pinned checksum) in run([build_sites, repro_checks, later]);
 (b) a `make all`-like invocation in which fetch_srdb is unreachable (network), then the later stage alone.
The later stage is a stand-in ordered after repro_checks (deps [features]; require_outputs on features.json)."""
import json
import logging
import os
import sys

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
import mshi.run as R  # noqa: E402
from mshi.data.fetch import srdb_csv_path  # noqa: E402
from mshi.io import read_json, require_outputs, result_staleness  # noqa: E402
from mshi.netutil import SourceUnavailableError  # noqa: E402

vc.stub_git()
ran = []


def later(c):
    require_outputs(c, "features.json", [c.path("interim", f"features_v3_{t}.parquet") for t in ("qc", "repo")])
    ran.append(1)
    return {"ok": True}


real = R._stages
R._stages = lambda: real() + [R.Stage("later_stage", later, ["features"], "later phase (stand-in)")]
B = lambda d: d["site_build"].__setitem__("merge_radius_km", 20.0)  # noqa: E731


def setup(name):
    s = vc.full_sand(vc.reset(vc.WORK / "v4" / name), B)
    vc.link_raw(s)
    vc.seed_committed(s, names=("cosore_annual.json",))      # COSORE annual does not depend on merge_radius_km
    assert R.run(["build_sites"], s) == 0
    vc.synthetic_rasters(s)
    vc.write_modis_stage(s, vc.synthetic_modis_table(s, noise_frac=0.19, seed=1))
    assert R.run(["features"], s) == 0
    n = len(vc.runlog(s))
    ran.clear()
    code = R.run(["repro_checks", "later_stage"], s)
    print(f"[{name}] control (B build current): run([repro_checks, later]) exit", code,
          {k: v[:90] for k, v in vc.statuses(s, n).items()}, vc.table(s)["summary"], "later ran:", len(ran))
    return s


# (a) build_sites errors in the invocation
s = setup("a")
p = srdb_csv_path(s)
os.unlink(p)                                    # the sandbox link only; the real file is untouched
p.write_bytes(srdb_csv_path(vc.CFG).read_bytes()[:-10])
n = len(vc.runlog(s))
ran.clear()
code = R.run(["build_sites", "repro_checks", "later_stage"], s)
print("[a] run([build_sites, repro_checks, later]) exit", code, {k: v[:90] for k, v in vc.statuses(s, n).items()},
      vc.table(s)["summary"], "later ran:", len(ran))
print("[a] build_sites.json staleness:", result_staleness(s, read_json(s.path("results", "build_sites.json"))),
      "| stored B build QC sites:", read_json(s.path("results", "build_sites.json"))["sites_qc"]["n"])
n = len(vc.runlog(s))
ran.clear()
print("[a] later stage alone afterwards: exit", R.run(["later_stage"], s), vc.statuses(s, n), "later ran:", len(ran),
      "| gate:", R._gate_status(s, {}, ["later_stage"]))

# (b) `make all`-like invocation, fetch_srdb unreachable; gridded fetches and COSORE are stand-ins (cached, current)
s = setup("b")


def unreachable(c):
    raise SourceUnavailableError("https://raw.githubusercontent.com/...: ConnectionError after 4 attempts", kind="unreachable")


stand = {"fetch_srdb": unreachable, "fetch_cosore": lambda c: {"stand_in": 1}, "cosore_annual": lambda c: {"stand_in": 1},
         "fetch_worldclim": lambda c: {"stand_in": 1}, "fetch_soilgrids": lambda c: {"stand_in": 1}}
base_stages = R._stages


def patched():
    out = []
    for st in base_stages():
        if st.name in stand:
            st.func = stand[st.name]
        out.append(st)
    return out


R._stages = patched
n = len(vc.runlog(s))
ran.clear()
names = [st.name for st in patched()]
code = R.run(names, s, full=True)
print("[b] make all (fetch_srdb unreachable): exit", code)
print("    statuses:", json.dumps({k: v[:80] for k, v in vc.statuses(s, n).items()}, indent=1))
print("    summary:", vc.table(s)["summary"], "later ran:", len(ran))
n = len(vc.runlog(s))
ran.clear()
print("[b] later stage alone afterwards: exit", R.run(["later_stage"], s), vc.statuses(s, n), "later ran:", len(ran),
      "| gate:", R._gate_status(s, {}, ["later_stage"]))
print("[b] features.json staleness:", result_staleness(s, read_json(s.path("results", "features.json"))),
      "| build_sites.json staleness:", result_staleness(s, read_json(s.path("results", "build_sites.json"))))
n = len(vc.runlog(s))
print("[b] control: run([repro_checks]) alone now: exit", R.run(["repro_checks"], s), vc.table(s)["summary"])
