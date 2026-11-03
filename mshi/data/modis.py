"""MODIS C6.1 NPP (MOD17A3HGF) and LST day/night (MOD11A2) window means at points, from Planetary Computer.

Port of ``docs/handoff/scripts/modis_points_lst.py``. For each point: the mean of valid pixels in a
0.05 x 0.05 deg window centred on the point, per raster; then the mean over rasters
(NPP: the 2020-2024 annual composites; LST: the first 8-day composite of each month, 2020-2024).

Planetary Computer pitfalls handled here (see PROMPT section 4):
- the SAS token is requested for the storage CONTAINER (modiseuwest/modis-061-cogs); the collection
  token returns 403;
- one token is shared across threads under a lock, refreshed every few minutes, and force-refreshed on 403;
- STAC items with ``datetime = None`` use ``start_datetime``;
- about 32 threads is safe.

Known quirk kept for fidelity (see docs/DECISIONS.md): reads are ``boundless`` with fill 0, and 0 is a
valid NPP value, so window cells beyond the edge of a MODIS tile count as NPP = 0.

Differences from the prototype (docs/DECISIONS.md DEV-P1-16). When every read succeeds and the catalog is
complete, items (1)-(5) and (7) change no value; (6) can change an LST mean, and only if two Terra items
share the earliest date of a month (each such tie is recorded):
(1) a read that still fails after its retries is retried once more in a second pass with a fresh token;
    if any read still fails, the stage FAILS and writes no values (the prototype printed the failure and
    averaged the remaining rasters, which silently changes a site's mean);
(2) the STAC search is checked before any raster is read: every tile must have one NPP item per year of
    ``datetime``, and in every month an LST composite dated in the first ``lst.composite_days`` days of the
    month (MOD11A2 composites start every 8 days, so a later first date means the month's first composite
    is missing), and no search may return ``max_items_per_tile`` items (possible truncation). A gap fails
    the stage, unless it is listed in ``sources.modis.accepted_catalog_gaps`` after review (the prototype
    averaged whatever was returned). Every gap is listed in results/modis_points.json;
(3) per-site means are taken over rasters in a fixed (kind, date, href) order, so the result does not
    depend on thread completion order (bit-reproducible);
(4) the output is cached in data/interim/ with a key: SHA-256 of ``sources.modis``, of the point set, of
    this module's source file and the versions of numpy, rasterio, GDAL, pyproj and PROJ. The sidecar also
    records the SHA-256 of the cached table. The cache is reused, and ``load_modis_points`` accepts the
    table, only if the key and the table's bytes match and the cached run had no failed reads;
(5) before extracting, the blob-storage host of the first asset is probed, so a policy block of the
    COG host is reported as ``blocked`` instead of producing all-NaN values;
(6) LST items are sorted by (date, id), so a same-date tie is broken by id (the prototype kept the
    API's order). Ties are counted and listed in results/modis_points.json;
(7) the STAC search returns items whose time span overlaps ``datetime``, so a composite dated before or
    after the range (e.g. one starting in late December 2019 that ends in January 2020, if the catalog
    dates it so; this could not be checked here) can be returned. As in the prototype it is used (NPP: its
    year; LST: its month counts as one more month); such periods are listed in results/modis_points.json
    (``periods_outside_datetime``).

Two stages share this code (docs/DECISIONS.md D-P2-13, which replaces D-P2-6). ``modis_points`` extracts the
reproduction's point set: every site of the locked build and the original 889 v1/v2 sites (NPP check); it
does not read the analysis build, so exploratory code cannot hold up the locked-test re-run or the NPP check.
``modis_points_analysis`` (Phase 2, exploratory, after the reproduction gate) extracts only the analysis sites
whose point is not in that set; ``features_analysis`` reads both tables. Window means are computed per point,
so splitting the points over two extractions changes no value. Each stage has its own cache
(data/interim/<stage>.parquet and .meta.json) and result (results/<stage>.json).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

from ..config import Config, canonical_sha256
from ..io import (StaleInputError, read_json, read_table, require_outputs, sha256_file, write_json, write_result,
                  write_table)

log = logging.getLogger("mshi.modis")


class ModisIncompleteError(RuntimeError):
    """Some raster reads failed after all retries, or the catalog lacks expected items; no values written."""


class StaleModisError(StaleInputError):
    """The cached MODIS table is missing, was not produced by the current MODIS config, code and libraries,
    changed after the extraction, or misses points (the run log records the reading stage as ``stale``)."""


def site_key(lat, lon, nd: int = 5) -> pd.Series:
    lat = pd.Series(np.asarray(lat, float)).round(nd).astype(str)
    lon = pd.Series(np.asarray(lon, float)).round(nd).astype(str)
    return lat + "_" + lon


class TokenCache:
    """One SAS token shared by all threads; refreshed every ``refresh_s`` seconds or on demand."""

    def __init__(self, url: str, refresh_s: float, session: requests.Session | None = None):
        self.url, self.refresh_s = url, refresh_s
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self._tok: tuple[str, float] | None = None

    def get(self, force: bool = False) -> str:
        with self._lock:
            if force or self._tok is None or time.time() - self._tok[1] > self.refresh_s:
                last = None
                for k in range(8):
                    try:
                        r = self.session.get(self.url, timeout=60)
                        r.raise_for_status()
                        self._tok = (r.json()["token"], time.time())
                        break
                    except Exception as e:  # noqa: BLE001 - network errors are retried
                        last = e
                        time.sleep(5 * (k + 1))
                if self._tok is None:
                    raise RuntimeError(f"could not obtain SAS token from {self.url}: {last}")
            return self._tok[0]


def sinusoidal_tiles(lon, lat, m: dict) -> tuple[np.ndarray, np.ndarray]:
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", m["sinusoidal_proj"], always_xy=True)
    x, y = tf.transform(np.asarray(lon, float), np.asarray(lat, float))
    h = np.floor((x - m["x_origin_m"]) / m["tile_size_m"]).astype(int)
    v = np.floor((m["y_origin_m"] - y) / m["tile_size_m"]).astype(int)
    return h, v


def scale_values(a: np.ndarray, kind: str, m: dict) -> np.ndarray:
    if kind == "npp":
        lo, hi = m["npp"]["valid_range"]
        return np.where((a >= lo) & (a <= hi), a * m["npp"]["scale"] + m["npp"]["offset"], np.nan)
    return np.where(a > m["lst"]["valid_min_exclusive"], a * m["lst"]["scale"] + m["lst"]["offset"], np.nan)


def read_windows(href: str, sub: pd.DataFrame, kind: str, m: dict) -> dict:
    """Window mean of valid pixels around each point of ``sub`` (columns site_key, lat, lon)."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds
    tf = Transformer.from_crs("EPSG:4326", m["sinusoidal_proj"], always_xy=True)
    half = m["window_deg"] / 2.0
    out = {}
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(href) as src:
            for p in sub.itertuples(index=False):
                xs, ys = tf.transform([p.lon - half, p.lon + half, p.lon - half, p.lon + half],
                                      [p.lat - half, p.lat - half, p.lat + half, p.lat + half])
                w = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
                a = src.read(1, window=w, boundless=True, fill_value=0).astype("float64")
                a = scale_values(a, "npp" if kind == "npp" else "lst", m)
                out[p.site_key] = float(np.nanmean(a)) if np.isfinite(a).any() else np.nan
    return out


def item_datetime(it):
    return it.datetime or pd.Timestamp(it.properties["start_datetime"]).to_pydatetime()


def expected_periods(m: dict) -> tuple[list[int], list[tuple[int, int]]]:
    """Years (NPP) and (year, month)s (LST) that ``sources.modis.datetime`` asks for."""
    start, end = (pd.Timestamp(x) for x in m["datetime"].split("/"))
    return (list(range(start.year, end.year + 1)),
            [(p.year, p.month) for p in pd.period_range(start, end, freq="M")])


def plan_jobs(pts: pd.DataFrame, m: dict, catalog, kinds: tuple[str, ...] = ("npp", "lst"),
              stats: dict | None = None) -> list[tuple]:
    """One job per (tile, raster): (kind, href, points in the tile, item datetime).

    NPP: every annual item in ``datetime``; LST: the first 8-day composite of each month (the only
    ``lst.composite`` rule implemented, as in the handoff). Items whose ``datetime`` is None use
    ``start_datetime``; only items whose id starts with the configured prefix (Terra) are used.
    ``stats`` (if given) receives ``catalog_gaps`` (``"h18v04 npp 2023"`` or ``"h18v04 lst 2022-05"``: an
    expected year or month with no item; ``"h18v04 lst 2021-01 first composite"``: the month's earliest
    composite is dated after day ``lst.composite_days``, so its first composite is missing;
    ``"h18v04 lst truncated"``: the search returned ``max_items_per_tile`` items), and, recorded but not
    failures, ``lst_same_date_ties``, ``npp_duplicate_years`` and ``periods_outside_datetime`` (years or
    months of returned items outside ``datetime``; they are used, as in the prototype).
    """
    if "lst" in kinds and m["lst"].get("composite") != "first_of_month":
        raise ValueError(f"sources.modis.lst.composite = {m['lst'].get('composite')!r} is not implemented; "
                         "only 'first_of_month' (the handoff rule) is")
    stats = {} if stats is None else stats
    gaps, ties, dups, outside = (stats.setdefault(k, []) for k in ("catalog_gaps", "lst_same_date_ties",
                                                                   "npp_duplicate_years",
                                                                   "periods_outside_datetime"))
    years, months = expected_periods(m)

    def items_for(col, prefix, h, v, tile, kind):
        q = {"modis:horizontal-tile": {"eq": int(h)}, "modis:vertical-tile": {"eq": int(v)}}
        its = list(catalog.search(collections=[col], datetime=m["datetime"], query=q,
                                  max_items=m["max_items_per_tile"]).item_collection())
        if len(its) >= m["max_items_per_tile"]:
            gaps.append(f"{tile} {kind} truncated")
        return [(item_datetime(i), i.id, i) for i in its if i.id.startswith(prefix)]

    jobs = []
    for (h, v), sub in pts.groupby(["h", "v"]):
        tile = f"h{int(h):02d}v{int(v):02d}"
        if "npp" in kinds:
            its = items_for(m["npp"]["collection"], m["npp"]["item_prefix"], h, v, tile, "npp")
            got = [d.year for d, _, _ in its]
            gaps += [f"{tile} npp {y}" for y in years if y not in got]
            dups += [f"{tile} npp {y}" for y in sorted(set(got)) if got.count(y) > 1]
            outside += [f"{tile} npp {y}" for y in sorted(set(got)) if y not in years]
            for d, _, it in its:
                jobs.append(("npp", it.assets[m["npp"]["asset"]].href, sub, d))
        if "lst" in kinds:
            its = sorted(items_for(m["lst"]["collection"], m["lst"]["item_prefix"], h, v, tile, "lst"),
                         key=lambda t: (t[0], t[1]))
            firsts: dict = {}
            same_date: dict = {}
            for d, iid, it in its:
                firsts.setdefault((d.year, d.month), (d, iid, it))
                same_date.setdefault(d, []).append(iid)
            gaps += [f"{tile} lst {y}-{mo:02d}" for y, mo in months if (y, mo) not in firsts]
            gaps += [f"{tile} lst {y}-{mo:02d} first composite" for (y, mo), (d, _, _) in sorted(firsts.items())
                     if (y, mo) in months and d.day > m["lst"]["composite_days"]]
            outside += [f"{tile} lst {y}-{mo:02d}" for y, mo in sorted(firsts) if (y, mo) not in months]
            for (y, mo), (d, iid, it) in sorted(firsts.items()):
                others = [j for j in same_date[d] if j != iid]
                if others:
                    ties.append({"tile": tile, "month": f"{y}-{mo:02d}", "chosen": iid, "others": others})
                for kind, asset in m["lst"]["assets"].items():
                    jobs.append((kind, it.assets[asset].href, sub, d))
    return jobs


def _read_job(job: tuple, tokens: TokenCache, m: dict, sleep=time.sleep) -> tuple[dict, str | None]:
    kind, href, sub, _when = job
    err: Exception | None = None
    for attempt in range(m["retries"]):
        try:
            return read_windows(href + "?" + tokens.get(), sub, kind, m), None
        except Exception as e:  # noqa: BLE001 - retried, then reported
            err = e
            if "403" in str(e):
                tokens.get(force=True)
            if attempt < m["retries"] - 1:
                sleep(3 * (attempt + 1))
    return {}, f"{href.split('?')[0]}: {type(err).__name__}: {str(err)[:200]}"


def aggregate(results: list[tuple], site_keys, kinds: list[str]) -> pd.DataFrame:
    """Per-site mean over rasters. ``results``: (kind, when, href, {site_key: window mean}) per raster.
    Values are accumulated in sorted (kind, when, href) order, so the means do not depend on the order
    in which reads completed."""
    acc: dict = {}
    for kind, _when, _href, vals in sorted(results, key=lambda r: (r[0], str(r[1]), r[2])):
        for k, val in vals.items():
            acc.setdefault((k, kind), []).append(val)
    rows = []
    for k in site_keys:
        row = {"site_key": k}
        for kind in kinds:
            v = np.array(acc.get((k, kind), []), float)
            row[kind] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
            row[kind + "_n"] = int(np.isfinite(v).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def extract_points(pts: pd.DataFrame, m: dict, kinds: tuple[str, ...] = ("npp", "lst"),
                   catalog=None, tokens: TokenCache | None = None) -> tuple[pd.DataFrame, dict]:
    """Window means for every point; returns (table, info): n_jobs (planned raster reads), n_reads (raster
    reads made), n_tiles, failed_reads, catalog_gaps (not accepted; if any, nothing is read and the table is
    empty), accepted_catalog_gaps, lst_same_date_ties, npp_duplicate_years, periods_outside_datetime."""
    from ..netutil import check_reachable
    pts = pts.copy()
    pts["h"], pts["v"] = sinusoidal_tiles(pts.lon.values, pts.lat.values, m)
    if catalog is None:
        import pystac_client
        catalog = pystac_client.Client.open(m["stac_url"])
    tokens = tokens or TokenCache(m["sas_token_url"], m["token_refresh_s"])
    stats: dict = {}
    jobs = plan_jobs(pts, m, catalog, kinds, stats=stats)
    n_tiles = int(pts.groupby(["h", "v"]).ngroups)
    accepted = set(m.get("accepted_catalog_gaps") or [])
    gaps = sorted(set(stats["catalog_gaps"]) - accepted)
    info = {"n_jobs": len(jobs), "n_tiles": n_tiles, "catalog_gaps": gaps,
            "accepted_catalog_gaps": sorted(set(stats["catalog_gaps"]) & accepted),
            "lst_same_date_ties": stats["lst_same_date_ties"], "npp_duplicate_years": stats["npp_duplicate_years"],
            "periods_outside_datetime": stats["periods_outside_datetime"]}
    if stats["periods_outside_datetime"]:
        log.warning("%d tile period(s) outside %s returned by the catalog, used as in the prototype (listed in "
                    "results/modis_points.json)", len(stats["periods_outside_datetime"]), m["datetime"])
    if stats["lst_same_date_ties"]:
        log.warning("%d month(s) have two Terra LST items on the earliest date; the smaller id is used (listed "
                    "in results/modis_points.json)", len(stats["lst_same_date_ties"]))
    if gaps:
        log.warning("catalog lacks %d expected item(s), e.g. %s; no raster read", len(gaps), gaps[:5])
        return pd.DataFrame(), {**info, "n_reads": 0, "failed_reads": []}
    log.info("%d points, %d tiles, %d raster reads", len(pts), n_tiles, len(jobs))
    if jobs and urlparse(jobs[0][1]).scheme in ("http", "https"):
        check_reachable(f"https://{urlparse(jobs[0][1]).netloc}/", require_ok=False)   # COG host
    results: list[tuple] = []

    def run_all(js: list[tuple], threads: int) -> list[tuple[tuple, str]]:
        bad = []
        with ThreadPoolExecutor(threads) as ex:
            futs = {ex.submit(_read_job, j, tokens, m): j for j in js}
            for f in as_completed(futs):
                j = futs[f]
                vals, err = f.result()
                if err:
                    bad.append((j, err))
                else:
                    results.append((j[0], j[3], j[1], vals))
        return bad

    bad = run_all(jobs, m["threads"])
    if bad:
        log.warning("%d of %d raster reads failed after %d attempts; second pass with a fresh token",
                    len(bad), len(jobs), m["retries"])
        tokens.get(force=True)
        bad = run_all([j for j, _ in bad], m["second_pass_threads"])
    failed = sorted(err for _, err in bad)
    for err in failed[:20]:
        log.warning("MODIS read FAILED: %s", err)
    all_kinds = (["npp"] if "npp" in kinds else []) + (list(m["lst"]["assets"]) if "lst" in kinds else [])
    out = aggregate(results, pts.site_key, all_kinds)
    return out, {**info, "n_reads": len(jobs), "failed_reads": failed}


LOCKED, ANALYSIS = "modis_points", "modis_points_analysis"          # stage, result and cache names


def _site_points(cfg: Config, prefix: str) -> list[pd.DataFrame]:
    return [read_table(cfg, cfg.path("derived", f"{prefix}_{tag}.parquet"))[["lat", "lon"]]
            for tag in cfg["site_build"]["variants"]]


def _unique_points(cfg: Config, frames: list[pd.DataFrame]) -> pd.DataFrame:
    pts = pd.concat([pd.DataFrame({"lat": f.lat.values, "lon": f.lon.values}) for f in frames], ignore_index=True)
    pts["site_key"] = site_key(pts.lat, pts.lon, cfg["features"]["site_key_round"]).values
    return pts.drop_duplicates("site_key").reset_index(drop=True)


def modis_point_set(cfg: Config) -> pd.DataFrame:
    """The reproduction's unique points (stage ``modis_points``): every site of the locked build (both variants)
    plus the original 889 v1/v2 sites (NPP check; not in smoke runs)."""
    frames = _site_points(cfg, "sites_v3")
    if cfg.out_root is None:          # not in smoke runs
        for rel in cfg["legacy_allowlist"]:
            o = read_table(cfg, cfg.repo_path(rel))
            frames.append(pd.DataFrame({"lat": o.latitude.values, "lon": o.longitude.values}))
    return _unique_points(cfg, frames)


def analysis_point_set(cfg: Config) -> pd.DataFrame:
    """The unique points of the analysis build (both variants) that are not in ``modis_point_set``
    (stage ``modis_points_analysis``)."""
    pts = _unique_points(cfg, _site_points(cfg, "sites_analysis"))
    return pts[~pts.site_key.isin(set(modis_point_set(cfg).site_key))].reset_index(drop=True)


def _extraction_code_sha256() -> str:
    """SHA-256 of this module's source file: any function in it can change the extracted values."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _library_versions() -> dict:
    import numpy
    import pyproj
    import rasterio
    return {"numpy": numpy.__version__, "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
            "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str}


KEY_FIELDS = ("modis_config_sha256", "code_sha256", "libraries")     # the parts that do not depend on points


def modis_cache_key(cfg: Config, keys) -> dict:
    return {"modis_config_sha256": canonical_sha256(cfg["sources"]["modis"]),
            "code_sha256": _extraction_code_sha256(), "libraries": _library_versions(),
            "points_sha256": hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest(),
            "n_points": int(len(keys))}


def write_modis_cache(cfg: Config, table: pd.DataFrame, key: dict, record: dict, name: str = LOCKED) -> Path:
    """Write the cached table and its sidecar (key, run record, SHA-256 of the table's bytes)."""
    out_path, meta_path = _paths(cfg, name)
    meta_path.unlink(missing_ok=True)
    table = table.copy()
    table.attrs = {}
    write_table(table, out_path)
    write_json({"key": key, "record": record, "parquet_sha256": sha256_file(out_path)}, meta_path)
    return out_path


def _paths(cfg: Config, name: str = LOCKED):
    return cfg.path("interim", f"{name}.parquet"), cfg.path("interim", f"{name}.meta.json")


def load_modis_points(cfg: Config, keys=None, name: str = LOCKED) -> pd.DataFrame:
    """The cached MODIS table of stage ``name``, only if it was produced by the current MODIS config, extraction
    code and libraries, with no failed reads, its bytes are those recorded in the sidecar, and it covers
    ``keys``; raises StaleModisError otherwise."""
    out_path, meta_path = _paths(cfg, name)
    if not (out_path.exists() and meta_path.exists()):
        raise StaleModisError(f"{out_path} (or its .meta.json) is missing; run stage {name}")
    meta = read_json(meta_path)
    k, cur = meta.get("key", {}), modis_cache_key(cfg, [])
    bad = [f for f in KEY_FIELDS if k.get(f) != cur[f]]
    if bad:
        raise StaleModisError(f"{out_path} was produced with a different {', '.join(bad)} (MODIS config, "
                              f"extraction code or libraries); re-run stage {name}")
    if meta.get("record", {}).get("n_failed_reads", 1) != 0:
        raise StaleModisError(f"{out_path} comes from a run with failed reads; re-run stage {name}")
    if meta.get("parquet_sha256") != sha256_file(out_path):
        raise StaleModisError(f"{out_path} changed after the extraction (SHA-256 differs from its .meta.json); "
                              f"re-run stage {name}")
    df = read_table(cfg, out_path)
    if keys is not None:
        miss = set(keys) - set(df.site_key)
        if miss:
            raise StaleModisError(f"{out_path} lacks {len(miss)} of the requested points; re-run {name}")
    return df


SITE_TABLES = ("sites_v3_qc.parquet", "sites_v3_repo.parquet")
ANALYSIS_SITE_TABLES = ("sites_analysis_qc.parquet", "sites_analysis_repo.parquet")


def modis_points(cfg: Config) -> dict:
    """Stage ``modis_points``: the reproduction's points (``modis_point_set``); reads only the locked build."""
    require_outputs(cfg, "build_sites.json", [cfg.path("derived", f) for f in SITE_TABLES])
    return _extract_stage(cfg, modis_point_set(cfg), LOCKED, ["build_sites.json"], {})


def modis_points_analysis(cfg: Config) -> dict:
    """Stage ``modis_points_analysis`` (Phase 2, exploratory): the analysis sites' points that ``modis_points``
    does not extract (``analysis_point_set``)."""
    require_outputs(cfg, "build_sites.json", [cfg.path("derived", f) for f in SITE_TABLES])
    require_outputs(cfg, "build_sites_analysis.json", [cfg.path("derived", f) for f in ANALYSIS_SITE_TABLES])
    return _extract_stage(cfg, analysis_point_set(cfg), ANALYSIS, ["build_sites.json", "build_sites_analysis.json"],
                          {"exploratory": True})


def _extract_stage(cfg: Config, pts: pd.DataFrame, name: str, ins: list[str], extra: dict) -> dict:
    """Extract (or reuse the cached extraction of) ``pts`` and record the result ``<name>.json``."""
    from ..netutil import check_reachable
    m = cfg["sources"]["modis"]
    key = modis_cache_key(cfg, pts.site_key)
    out_path, meta_path = _paths(cfg, name)
    if out_path.exists() and meta_path.exists():
        meta = read_json(meta_path)
        if (meta.get("key") == key and meta.get("record", {}).get("n_failed_reads") == 0
                and meta.get("parquet_sha256") == sha256_file(out_path)):
            log.info("%s: cached extraction matches the MODIS config, code, libraries and %d points", name, len(pts))
            write_result(cfg, meta["record"], f"{name}.json", outputs=[out_path], inputs=ins)  # same record
            return {**meta["record"], "cached": True}
    if pts.empty:                     # nothing to extract (e.g. every analysis point is in the locked set)
        cols = {"site_key": pd.Series(dtype=str)}          # the columns ``aggregate`` writes, in its order
        for k in ["npp", *m["lst"]["assets"]]:
            cols[k], cols[f"{k}_n"] = pd.Series(dtype=float), pd.Series(dtype="int64")
        vals = pd.DataFrame(cols)
        rec = {**extra, "n_points": 0, "n_failed_reads": 0, "failed_reads": [], "cache_key": key}
        write_modis_cache(cfg, vals, key, rec, name)
        write_result(cfg, rec, f"{name}.json", outputs=[out_path], inputs=ins)
        return rec
    # A stale cache is left in place until a new extraction replaces it (write_modis_cache): if the sources
    # cannot be reached, readers still see why the old table is refused (load_modis_points).
    check_reachable(m["stac_url"])
    check_reachable(m["sas_token_url"])
    vals, info = extract_points(pts, m)
    failed, gaps = info["failed_reads"], info["catalog_gaps"]
    rec = {**extra, "n_points": int(len(pts)), "n_tiles": info["n_tiles"], "n_planned_reads": info["n_jobs"],
           "n_raster_reads": info["n_reads"],
           "n_failed_reads": len(failed), "failed_reads": failed[:100], "cache_key": key,
           "n_catalog_gaps": len(gaps), "catalog_gaps": gaps,          # complete: copied after review
           "accepted_catalog_gaps": info["accepted_catalog_gaps"],
           "lst_same_date_ties": {"n": len(info["lst_same_date_ties"]), "list": info["lst_same_date_ties"][:200]},
           "npp_duplicate_years": info["npp_duplicate_years"],
           "periods_outside_datetime": {"n": len(info["periods_outside_datetime"]),
                                        "list": info["periods_outside_datetime"]},
           "missing": {c: int(vals[c].isna().sum()) for c in ["npp", "lst_day", "lst_night"] if c in vals}}
    if failed or gaps:
        out_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        write_result(cfg, {**rec, "status": "incomplete: no values written"}, f"{name}.json", inputs=ins)
        why = (f"the STAC catalog lacks {len(gaps)} expected item(s) (first: {gaps[0]}); after review, list "
               "genuine gaps in sources.modis.accepted_catalog_gaps (and log the decision)" if gaps else
               f"{len(failed)} of {info['n_jobs']} MODIS raster reads failed after retries (first: {failed[0]})")
        raise ModisIncompleteError(f"{why}; no values written, see results/{name}.json")
    write_modis_cache(cfg, vals, key, rec, name)
    write_result(cfg, rec, f"{name}.json", outputs=[out_path], inputs=ins)
    return rec
