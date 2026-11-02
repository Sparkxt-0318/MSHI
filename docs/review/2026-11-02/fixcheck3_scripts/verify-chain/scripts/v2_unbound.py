"""Claim 2: results are not bound to the inputs they read. Same config and code; an upstream stage re-run that
writes different bytes (unpinned external source re-fetched after the gitignored caches were lost).
(A) SoilGrids re-download returns other rasters (real fetch_soilgrids, download patched) and MODIS re-extraction
    returns other NPP values (real modis_points, extract_points patched) -> real features stage.
Then: which results are current? does the stored table still pass, the gate open, the regression tests pass?
What does a fresh repro_checks say about the locked-test rows?"""
import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "fixcheck3_scripts/verify-chain/scripts")
import vc  # noqa: E402
import numpy as np  # noqa: E402

logging.basicConfig(level=logging.ERROR)
import mshi.data.modis as M  # noqa: E402
import mshi.data.rasters as RA  # noqa: E402
import mshi.netutil as N  # noqa: E402
import mshi.run as R  # noqa: E402
from mshi.io import read_json, require_outputs, result_staleness, sha256_file  # noqa: E402

base = vc.reset(vc.WORK / "v2")
sand = vc.full_sand(base / "s")
vc.seed_committed(sand)
vc.synthetic_rasters(sand)
vc.write_modis_stage(sand, vc.synthetic_modis_table(sand, noise_frac=0.19, seed=1))
print("features exit:", R.run(["features"], sand))
vc.locked_reruns(sand)
print("repro exit (author state):", R.run(["repro_checks"], sand), vc.table(sand)["summary"],
      "r", round(vc.table(sand)["npp_check"]["pearson_r"], 4))
feat0 = {t: sha256_file(sand.path("interim", f"features_v3_{t}.parquet")) for t in ("qc", "repo")}
md0 = sand.path("results", "reproduction_check.md").read_bytes()
json0 = sand.path("results", "reproduction_check.json").read_bytes()
ct0 = {t: sand.path("results", f"clean_test_rerun_{t}.json").read_bytes() for t in ("qc", "repo")}

# a later-phase stand-in stage (ordered after repro_checks), reading the feature tables through require_outputs
ran = []


def later(c):
    require_outputs(c, "features.json", [c.path("interim", f"features_v3_{t}.parquet") for t in ("qc", "repo")])
    ran.append(1)
    return {"ok": True}


real = R._stages
R._stages = lambda: real() + [R.Stage("later_stage", later, ["features"], "later phase (stand-in)")]

# ---- gitignored roots lost (fresh clone / cleaned caches)
for r in ("interim", "raw"):
    shutil.rmtree(sand.path(r))
# WorldClim: the same rasters again (stand-in for an identical re-download), recorded by its fetch result
import rasterio  # noqa: E402
lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
rng = np.random.default_rng(0)
wc = []
for i in range(1, 20):
    v = 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2
    p = RA.worldclim_path(sand, i)
    vc.wgs_raster(p, v + rng.normal(0, 0.1, v.shape))
    wc.append(p)
from mshi.io import write_result  # noqa: E402
write_result(sand, {"synthetic": True}, "fetch_worldclim.json", outputs=wc)

# SoilGrids: the real stage; the WCS now returns other values (unpinned source, same config and code)
tmpdir = base / "wcs"
tmpdir.mkdir()


def fake_download(url, dest, params=None, session=None, **k):
    cov = params["COVERAGEID"]
    t = tmpdir / (cov + ".tif")
    vc.wgs_raster(t, 140 + 80 * np.sin(np.radians(lat)) ** 2 + 30 * np.cos(np.radians(lon)), dtype="int16")
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(t, dest)
    return {"path": str(dest), "sha256": None, "downloaded": True}


RA.download = fake_download
# MODIS: the real stage; the live catalog now gives other NPP values (same config, code, libraries)
changed = vc.synthetic_modis_table(sand, noise_frac=1.5, seed=7)
N.check_reachable = lambda *a, **k: None
M.extract_points = lambda pts, m, **k: (changed.set_index("site_key").loc[pts.site_key].reset_index(),
                                        {"failed_reads": [], "catalog_gaps": [], "n_tiles": 1, "n_jobs": 1,
                                         "accepted_catalog_gaps": [], "lst_same_date_ties": [],
                                         "npp_duplicate_years": []})
n = len(vc.runlog(sand))
code = R.run(["fetch_soilgrids", "modis_points", "features"], sand)
print("\n`make features`-like re-run: exit", code, vc.statuses(sand, n))
print("staleness:", json.dumps(vc.staleness_all(sand), indent=1))
print("feature tables changed:", {t: sha256_file(sand.path("interim", f"features_v3_{t}.parquet")) != feat0[t] for t in feat0})
print("clean_test_rerun_*.json unchanged on disk:", {t: sand.path("results", f"clean_test_rerun_{t}.json").read_bytes() == ct0[t] for t in ct0})
print("stored table unchanged:", sand.path("results", "reproduction_check.json").read_bytes() == json0,
      sand.path("results", "reproduction_check.md").read_bytes() == md0)
print("gate:", R._gate_status(sand, {}, ["later_stage"]))
n = len(vc.runlog(sand))
print("later stage alone: exit", R.run(["later_stage"], sand), vc.statuses(sand, n), "ran", len(ran))
print("regression (stored table):", json.dumps(vc.regression(sand), indent=1))
print("stored npp r:", round(read_json(sand.path("results", "reproduction_check.json"))["npp_check"]["pearson_r"], 4))

# ---- a fresh repro_checks alone (`make repro`)
n = len(vc.runlog(sand))
code = R.run(["repro_checks"], sand)
print("\nmake repro: exit", code, {k: v[:120] for k, v in vc.statuses(sand, n).items()})
t = vc.table(sand)
print("summary:", t["summary"])
for r in t["rows"]:
    if r["quantity"].startswith(("Locked", "NPP")):
        print("   ", r["status"], "|", r["quantity"][:70], "|", r["v3"])
