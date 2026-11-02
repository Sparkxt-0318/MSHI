"""Helpers for the adversarial verification of the 'chain' claims (scratch only; the repository is read-only).

Run every script as: GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 /home/user/MSHI/.venv/bin/python -I -B <script>
"""
import copy
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path("/home/user/MSHI")
SCR = Path("fixcheck3_scripts/verify-chain")
WORK = SCR / "work"
for p in (str(REPO), str(SCR / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

from mshi.config import Config, load_config  # noqa: E402

CFG = load_config()


def reset(path: Path) -> Path:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def full_sand(root: Path, edit=None) -> Config:
    """Non-smoke sandbox (out_root None): raw/interim/derived/results/figures are absolute scratch paths."""
    data = copy.deepcopy(CFG.data)
    for r in ("raw", "interim", "derived", "results", "figures"):
        data["paths"][r] = str(root / r)
    if edit:
        edit(data)
    return Config(data, source=CFG.source)


def smoke_sand(root: Path, edit=None) -> Config:
    data = copy.deepcopy(CFG.data)
    data["paths"]["raw"] = str(root / "raw")
    if edit:
        edit(data)
    return Config(data, source=CFG.source, out_root=root / "out")


def committed(name: str) -> dict:
    d = json.loads((REPO / "results" / name).read_text())
    d.pop("_provenance", None)
    d.pop("_outputs", None)
    return d


OUTS = {"cosore_annual.json": ["cosore_annual.csv"],
        "build_sites.json": ["records_v3.parquet", "sites_v3_qc.parquet", "sites_v3_repo.parquet"]}


def seed_committed(sand: Config, names=("cosore_annual.json", "build_sites.json")) -> None:
    """Copy the committed derived tables into the sandbox and write the committed results (values as committed)
    under the sandbox config, recording those tables as outputs: the committed state, as produced under this
    sandbox config (the sandbox config hash differs from the real one because its paths differ)."""
    from mshi.io import write_result
    for n in names:
        ps = []
        for f in OUTS.get(n, []):
            dst = sand.path("derived", f)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / "data" / "derived" / f, dst)
            ps.append(dst)
        write_result(sand, committed(n), n, outputs=ps)


def link_raw(sand: Config) -> None:
    """Symlink the pinned SRDB CSV (+LICENSE) and Natural Earth files into the sandbox raw root (read only)."""
    from mshi.data.fetch import naturalearth_path, srdb_csv_path
    pairs = [(srdb_csv_path(CFG), srdb_csv_path(sand)),
             (srdb_csv_path(CFG).with_name("LICENSE"), srdb_csv_path(sand).with_name("LICENSE"))]
    for f in CFG["sources"]["naturalearth"]["files"]:
        pairs.append((naturalearth_path(CFG, f), naturalearth_path(sand, f)))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() and not dst.is_symlink():
            os.symlink(src, dst)


def wgs_raster(path: Path, values, dtype="float32") -> None:
    import rasterio
    from rasterio.transform import from_origin
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(-180, 90, 1, 1)) as dst:
        dst.write(values.astype(dtype), 1)


def synthetic_rasters(sand: Config, seed: int = 0) -> None:
    """Synthetic 1-deg global rasters at the real raster paths, recorded as the fetch stages' outputs."""
    import numpy as np
    from mshi.data.rasters import soilgrids_path, worldclim_path
    from mshi.io import write_result
    rng = np.random.default_rng(seed)
    lat = np.linspace(89.5, -89.5, 180)[:, None] * np.ones((1, 360))
    lon = np.ones((180, 1)) * np.linspace(-179.5, 179.5, 360)[None, :]
    wc = []
    for i in range(1, sand["features"]["worldclim_vars"] + 1):
        v = 25 - 0.4 * np.abs(lat) + i if i != 12 else 300 + 2000 * np.cos(np.radians(lat)) ** 2
        p = worldclim_path(sand, i)
        wgs_raster(p, v + rng.normal(0, 0.1, v.shape))
        wc.append(p)
    sg = []
    for k in sand["sources"]["soilgrids"]["variables"]:
        p = soilgrids_path(sand, k)
        wgs_raster(p, 100 + 50 * np.cos(np.radians(lon)) ** 2, dtype="int16")
        sg.append(p)
    write_result(sand, {"synthetic": True}, "fetch_worldclim.json", outputs=wc)
    write_result(sand, {"synthetic": True}, "fetch_soilgrids.json", outputs=sg)


def synthetic_modis_table(sand: Config, noise_frac: float, seed: int):
    """MODIS values over the stage's own point set; NPP at the original sites = committed NPP + noise
    (noise_frac x the committed NPP's SD), so the NPP r is near a chosen value. Synthetic targets only."""
    import numpy as np
    import pandas as pd
    from mshi.data.modis import modis_point_set, site_key
    from mshi.io import read_table
    nd = sand["features"]["site_key_round"]
    pts = modis_point_set(sand)
    o = pd.concat([read_table(sand, sand.repo_path(rel)) for rel in sand["legacy_allowlist"]], ignore_index=True)
    o["site_key"] = site_key(o.latitude, o.longitude, nd).values
    o = o.drop_duplicates("site_key")
    rng = np.random.default_rng(seed)
    base = o.set_index("site_key")["npp"]
    npp = pd.Series(rng.normal(600, 200, len(pts)), index=pts.site_key.values)
    common = base.index.intersection(npp.index)
    have = base.loc[common].notna()
    sd = float(base.std())
    npp.loc[common[have.values]] = base.loc[common[have.values]].values + rng.normal(0, noise_frac * sd, int(have.sum()))
    return pd.DataFrame({"site_key": pts.site_key.values, "npp": npp.values, "npp_n": 5,
                         "lst_day": 20 - 0.3 * pts.lat.abs().values, "lst_night": 5 - 0.3 * pts.lat.abs().values})


def write_modis_stage(sand: Config, table) -> None:
    """What modis_points leaves after a complete extraction: cache + sidecar + modis_points.json recording the parquet."""
    from mshi.data.modis import modis_cache_key, write_modis_cache
    from mshi.io import write_result
    key = modis_cache_key(sand, table.site_key)
    rec = {"n_points": int(len(table)), "n_failed_reads": 0, "cache_key": key, "synthetic": True}
    out = write_modis_cache(sand, table, key, rec)
    write_result(sand, rec, "modis_points.json", outputs=[out])


def locked_reruns(sand: Config) -> None:
    """clean_test_rerun_<v>.json = the locked results + an 'identical' vs_locked block (nothing is scored)."""
    from mshi.io import write_result
    lr = sand["clean_test"]["locked_results"]
    for t, f in lr.items():
        locked = json.loads(sand.repo_path(f["file"]).read_text())
        write_result(sand, {**locked, "variant": t,
                            "vs_locked": {"identical": True, "selected_same": True, "max_abs_primary_diff": 0.0},
                            "lock": {"locked_sha256": sand["clean_test"]["locked_sha256"]}},
                     f"clean_test_rerun_{t}.json")


def runlog(sand: Config) -> list:
    p = sand.path("results", "run_log.jsonl")
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def statuses(sand: Config, since: int = 0) -> dict:
    return {r["stage"]: r["status"][:160] for r in runlog(sand)[since:]}


def table(sand: Config) -> dict:
    return json.loads(sand.path("results", "reproduction_check.json").read_text())


def staleness_all(sand: Config) -> dict:
    from mshi.io import read_json, result_staleness
    return {p.name: result_staleness(sand, read_json(p)) for p in sorted(sand.path("results").glob("*.json"))
            if p.name != "environment.json"}


def regression(sand: Config, names=None) -> dict:
    """Call the tests/test_regression.py functions with the sandbox config (pytest skip/fail are BaseException)."""
    sys.path.insert(0, str(REPO / "tests"))
    import test_regression as TR
    names = names or ["test_cosore_sites", "test_record_and_site_counts", "test_locked_test_rerun",
                      "test_npp_correlation", "test_reproduction_table_has_no_fail"]
    out = {}
    for t in names:
        try:
            getattr(TR, t)(sand)
            out[t] = "pass"
        except BaseException as e:  # noqa: BLE001
            out[t] = f"{type(e).__name__}: {str(e)[:140]}"
    for v in ("qc", "repo"):
        try:
            TR.test_locked_rerun_reported_against_locked_result(sand, v)
            out[f"rerun_reported_{v}"] = "pass"
        except BaseException as e:  # noqa: BLE001
            out[f"rerun_reported_{v}"] = f"{type(e).__name__}: {str(e)[:140]}"
    return out


def stub_git() -> None:
    """Never run git inside data/raw (the COSORE checkout is downloaded data)."""
    import mshi.netutil as N
    N.verify_git_checkout = lambda dest, commit: {"commit": commit, "tree": "stub"}
