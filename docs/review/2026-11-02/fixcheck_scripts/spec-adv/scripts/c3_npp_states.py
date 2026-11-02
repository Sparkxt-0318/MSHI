"""Claim 3: NPP / re-run-identical row statuses in repro_checks for (a) a stale modis_points.json,
(b) a current MODIS table whose NPP cannot be correlated, (c) a re-run JSON without / with a malformed vs_locked.

Usage: python -B c3_npp_states.py <sandbox_dir>
All outputs go to the sandbox (out_root). No locked test is run; re-run JSONs are copies of the locked file.
"""
import copy
import json
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")
sys.path.insert(0, "/home/user/MSHI/tests")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mshi.config import Config, load_config  # noqa: E402
from mshi.io import write_json, write_result, write_table  # noqa: E402
from mshi.analysis import repro_checks as RC  # noqa: E402
from mshi.data import modis as M  # noqa: E402
import test_regression as TR  # noqa: E402

ROOT = Path(sys.argv[1])
shutil.rmtree(ROOT, ignore_errors=True)
base = load_config()
locked_qc = json.loads(base.path("handoff", "results", "clean_test_europe.json").read_text())


def mk(name, edit=None):
    d = copy.deepcopy(base.data)
    d["paths"]["raw"] = str(ROOT / name / "raw")
    if edit:
        edit(d)
    return Config(d, source=base.source, out_root=ROOT / name / "out")


def common(c, vs=True):
    for f in ["build_sites.json", "cosore_annual.json"]:
        o = json.loads(base.path("results", f).read_text())
        o.pop("_provenance")
        write_result(c, o, f)
    qc = copy.deepcopy(locked_qc)
    if vs is True:
        qc["vs_locked"] = {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0}
    elif vs is not None:
        qc["vs_locked"] = vs
    write_result(c, qc, "clean_test_rerun_qc.json")


def modis_table(c, df):
    write_table(df, c.path("interim", "modis_points.parquet"))
    write_json({"key": M.modis_cache_key(c, df.site_key), "record": {"n_failed_reads": 0}},
               c.path("interim", "modis_points.meta.json"))


def legacy_keys(c):
    frames = [pd.read_parquet(c.repo_path(rel)) for rel in c["legacy_allowlist"]]
    o = pd.concat(frames, ignore_index=True)
    return o, M.site_key(o.latitude, o.longitude, c["features"]["site_key_round"]).values


def run_tests(c):
    out = {}
    for t in ("test_npp_correlation", "test_reproduction_table_has_no_fail", "test_locked_rerun_reported_against_locked_result"):
        try:
            getattr(TR, t)(c)
            out[t] = "passed"
        except BaseException as e:  # noqa: BLE001 - pytest outcomes are BaseException subclasses
            out[t] = f"{type(e).__name__}: {str(e)[:90]}"
    return out


def show(tag, c):
    try:
        s = RC.repro_checks(c)
    except BaseException as e:  # noqa: BLE001
        print(f"[{tag}] repro_checks raised {type(e).__name__}: {e}")
        p = c.path("results", "reproduction_check.json")
        print(f"[{tag}] reproduction_check.json exists after the error: {p.exists()}")
        return
    rows = json.loads(c.path("results", "reproduction_check.json").read_text())["rows"]
    print(f"[{tag}] summary {s}")
    for r in rows:
        if r["quantity"].startswith(("NPP", "Original sites", "Locked test: re-run")):
            print(f"[{tag}]   {r['status']:8s} | {r['quantity'][:55]} | v3={r['v3']} | note={r['note'][:110]!r}")
    print(f"[{tag}] tests: {run_tests(c)}")


# (a) modis_points.json produced under another config; MODIS table itself current and correlatable
a = mk("a")
common(a)
o, keys = legacy_keys(a)
df = pd.DataFrame({"site_key": keys, "npp": o["npp"].to_numpy(float) * 0.1, "npp_n": 5, "lst_day": 10.0,
                   "lst_day_n": 60, "lst_night": 1.0, "lst_night_n": 60}).drop_duplicates("site_key")
modis_table(a, df)
other = mk("a", edit=lambda d: d["smoke"].__setitem__("seed", 1))       # any other config
write_result(other, {"n_points": len(df), "n_failed_reads": 0}, "modis_points.json")
show("a stale modis_points.json", a)

# (a') control: the same with a current modis_points.json
a2 = mk("a2")
common(a2)
modis_table(a2, df)
write_result(a2, {"n_points": len(df), "n_failed_reads": 0}, "modis_points.json")
show("a' current modis_points.json", a2)

# (b) MODIS extraction current, but no site with NPP in both tables (all-NaN NPP from the extraction)
b = mk("b")
common(b)
dfb = df.copy()
dfb["npp"] = np.nan
modis_table(b, dfb)
write_result(b, {"n_points": len(dfb), "n_failed_reads": 0}, "modis_points.json")
show("b current, all-NaN NPP", b)

# (b2) key mismatch (site_key rounded differently) -> no overlap
b2 = mk("b2")
common(b2)
dfk = df.copy()
dfk["site_key"] = dfk.site_key + "x"
modis_table(b2, dfk)
write_result(b2, {"n_points": len(dfk), "n_failed_reads": 0}, "modis_points.json")
show("b2 current, no key overlap", b2)

# (c) re-run JSON without vs_locked
cc = mk("c")
common(cc, vs=None)
show("c no vs_locked", cc)

# (c2) vs_locked identical False and max_abs_primary_diff None
c2 = mk("c2")
common(c2, vs={"identical": False, "selected_same": True, "max_abs_primary_diff": None})
show("c2 malformed vs_locked", c2)

# can compare_with_locked produce max_abs_primary_diff None with identical False today?
from mshi.analysis.clean_test import compare_with_locked  # noqa: E402
R = copy.deepcopy(locked_qc)
print("compare_with_locked(locked, locked):", {k: compare_with_locked(R, locked_qc)[k] for k in ("identical", "max_abs_primary_diff")})
R_noprim = {k: v for k, v in R.items() if k != "primary"}
print("compare_with_locked(no primary):", {k: compare_with_locked(R_noprim, locked_qc)[k] for k in ("identical", "max_abs_primary_diff")})
