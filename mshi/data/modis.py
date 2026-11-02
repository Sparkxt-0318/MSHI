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

Differences from the prototype (none changes a value when every read succeeds; docs/DECISIONS.md):
- a read that still fails after its retries is retried once more in a second pass with a fresh token;
  if any read still fails, the stage FAILS and writes no values (the prototype printed the failure and
  averaged the remaining rasters, which silently changes a site's mean);
- per-site means are taken over rasters in a fixed (kind, date, href) order, so the result does not
  depend on thread completion order (bit-reproducible);
- the output is cached in data/interim/ together with a key (SHA-256 of ``sources.modis``, of the point
  set and of the extraction code); the cache is reused only if the key matches exactly and the cached
  run had no failed reads, and ``load_modis_points`` refuses a table whose key does not match;
- before extracting, the blob-storage host of the first asset is probed, so a policy block of the
  COG host is reported as ``blocked`` instead of producing all-NaN values.
"""
from __future__ import annotations

import hashlib
import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

from ..config import Config, canonical_sha256
from ..io import read_json, read_table, write_json, write_result, write_table

log = logging.getLogger("mshi.modis")


class ModisIncompleteError(RuntimeError):
    """Some raster reads failed after all retries; no values were written."""


class StaleModisError(RuntimeError):
    """The cached MODIS table was not produced by the current MODIS config/code, or misses points."""


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


def plan_jobs(pts: pd.DataFrame, m: dict, catalog, kinds: tuple[str, ...] = ("npp", "lst")) -> list[tuple]:
    """One job per (tile, raster): (kind, href, points in the tile, item datetime).

    NPP: every annual item in ``datetime``; LST: the first 8-day composite of each month (the only
    ``lst.composite`` rule implemented, as in the handoff). Items whose ``datetime`` is None use
    ``start_datetime``; only items whose id starts with the configured prefix (Terra) are used.
    """
    if "lst" in kinds and m["lst"].get("composite") != "first_of_month":
        raise ValueError(f"sources.modis.lst.composite = {m['lst'].get('composite')!r} is not implemented; "
                         "only 'first_of_month' (the handoff rule) is")

    def items_for(col, prefix, h, v):
        q = {"modis:horizontal-tile": {"eq": int(h)}, "modis:vertical-tile": {"eq": int(v)}}
        its = catalog.search(collections=[col], datetime=m["datetime"], query=q,
                             max_items=m["max_items_per_tile"]).item_collection()
        return [i for i in its if i.id.startswith(prefix)]

    jobs = []
    for (h, v), sub in pts.groupby(["h", "v"]):
        if "npp" in kinds:
            for it in items_for(m["npp"]["collection"], m["npp"]["item_prefix"], h, v):
                jobs.append(("npp", it.assets[m["npp"]["asset"]].href, sub, item_datetime(it)))
        if "lst" in kinds:
            firsts = {}
            for it in sorted(items_for(m["lst"]["collection"], m["lst"]["item_prefix"], h, v),
                             key=lambda i: (item_datetime(i), i.id)):
                firsts.setdefault((item_datetime(it).year, item_datetime(it).month), it)
            for it in firsts.values():
                for kind, asset in m["lst"]["assets"].items():
                    jobs.append((kind, it.assets[asset].href, sub, item_datetime(it)))
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
    """Window means for every point; returns (table, info) with info = n_jobs, n_tiles, failed_reads."""
    from ..netutil import check_reachable
    pts = pts.copy()
    pts["h"], pts["v"] = sinusoidal_tiles(pts.lon.values, pts.lat.values, m)
    if catalog is None:
        import pystac_client
        catalog = pystac_client.Client.open(m["stac_url"])
    tokens = tokens or TokenCache(m["sas_token_url"], m["token_refresh_s"])
    jobs = plan_jobs(pts, m, catalog, kinds)
    n_tiles = int(pts.groupby(["h", "v"]).ngroups)
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
    return out, {"n_jobs": len(jobs), "n_tiles": n_tiles, "failed_reads": failed}


def modis_point_set(cfg: Config) -> pd.DataFrame:
    """Unique points: every v3 site (both variants) plus the original 889 v1/v2 sites (NPP check)."""
    nd = cfg["features"]["site_key_round"]
    frames = []
    for tag in cfg["site_build"]["variants"]:
        st = read_table(cfg, cfg.path("derived", f"sites_v3_{tag}.parquet"))
        frames.append(pd.DataFrame({"lat": st.lat.values, "lon": st.lon.values}))
    if cfg.out_root is None:          # not in smoke runs
        for rel in cfg["legacy_allowlist"]:
            o = read_table(cfg, cfg.repo_path(rel))
            frames.append(pd.DataFrame({"lat": o.latitude.values, "lon": o.longitude.values}))
    pts = pd.concat(frames, ignore_index=True)
    pts["site_key"] = site_key(pts.lat, pts.lon, nd).values
    return pts.drop_duplicates("site_key").reset_index(drop=True)


def _extraction_code_sha256() -> str:
    """Hash of the source of the functions that determine the extracted values."""
    src = "".join(inspect.getsource(f) for f in (site_key, sinusoidal_tiles, scale_values, read_windows,
                                                 item_datetime, plan_jobs, _read_job, aggregate))
    return hashlib.sha256(src.encode()).hexdigest()


def modis_cache_key(cfg: Config, keys) -> dict:
    return {"modis_config_sha256": canonical_sha256(cfg["sources"]["modis"]),
            "code_sha256": _extraction_code_sha256(),
            "points_sha256": hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest(),
            "n_points": int(len(keys))}


def _paths(cfg: Config):
    return cfg.path("interim", "modis_points.parquet"), cfg.path("interim", "modis_points.meta.json")


def load_modis_points(cfg: Config, keys=None) -> pd.DataFrame:
    """The cached MODIS table, only if it was produced by the current MODIS config and extraction code,
    with no failed reads, and covers ``keys``; raises StaleModisError otherwise."""
    out_path, meta_path = _paths(cfg)
    if not (out_path.exists() and meta_path.exists()):
        raise FileNotFoundError(f"{out_path} (or its .meta.json) missing; run stage modis_points")
    meta = read_json(meta_path)
    k = meta.get("key", {})
    if (k.get("modis_config_sha256") != canonical_sha256(cfg["sources"]["modis"])
            or k.get("code_sha256") != _extraction_code_sha256()):
        raise StaleModisError(f"{out_path} was produced with a different MODIS config or extraction code; "
                              "re-run stage modis_points")
    if meta.get("record", {}).get("n_failed_reads", 1) != 0:
        raise StaleModisError(f"{out_path} comes from a run with failed reads; re-run stage modis_points")
    df = read_table(cfg, out_path)
    if keys is not None:
        miss = set(keys) - set(df.site_key)
        if miss:
            raise StaleModisError(f"{out_path} lacks {len(miss)} of the requested points; re-run modis_points")
    return df


def modis_points(cfg: Config) -> dict:
    from ..netutil import check_reachable
    m = cfg["sources"]["modis"]
    pts = modis_point_set(cfg)
    key = modis_cache_key(cfg, pts.site_key)
    out_path, meta_path = _paths(cfg)
    if out_path.exists() and meta_path.exists():
        meta = read_json(meta_path)
        if meta.get("key") == key and meta.get("record", {}).get("n_failed_reads") == 0:
            log.info("modis_points: cached extraction matches the MODIS config, code and %d points", len(pts))
            write_result(cfg, meta["record"], "modis_points.json")     # same record as the original run
            return {**meta["record"], "cached": True}
    meta_path.unlink(missing_ok=True)
    check_reachable(m["stac_url"])
    check_reachable(m["sas_token_url"])
    vals, info = extract_points(pts, m)
    failed = info["failed_reads"]
    rec = {"n_points": int(len(pts)), "n_tiles": info["n_tiles"], "n_raster_reads": info["n_jobs"],
           "n_failed_reads": len(failed), "failed_reads": failed[:100], "cache_key": key,
           "missing": {c: int(vals[c].isna().sum()) for c in ["npp", "lst_day", "lst_night"] if c in vals}}
    if len(failed) > m["max_failed_reads"]:
        out_path.unlink(missing_ok=True)
        write_result(cfg, {**rec, "status": "incomplete: no values written"}, "modis_points.json")
        raise ModisIncompleteError(f"{len(failed)} of {info['n_jobs']} MODIS raster reads failed after retries "
                                   f"(first: {failed[0]}); no values written, see results/modis_points.json")
    vals.attrs = {}
    write_table(vals, out_path)
    write_json({"key": key, "record": rec}, meta_path)
    write_result(cfg, rec, "modis_points.json")
    return rec
