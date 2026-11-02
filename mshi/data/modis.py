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
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

from ..config import Config
from ..io import read_table, write_json, write_table

log = logging.getLogger("mshi.modis")


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
    def items_for(col, prefix, h, v):
        q = {"modis:horizontal-tile": {"eq": int(h)}, "modis:vertical-tile": {"eq": int(v)}}
        its = catalog.search(collections=[col], datetime=m["datetime"], query=q,
                             max_items=m["max_items_per_tile"]).item_collection()
        return [i for i in its if i.id.startswith(prefix)]

    jobs = []
    for (h, v), sub in pts.groupby(["h", "v"]):
        if "npp" in kinds:
            for it in items_for(m["npp"]["collection"], m["npp"]["item_prefix"], h, v):
                jobs.append(("npp", it.assets[m["npp"]["asset"]].href, sub, item_datetime(it).year))
        if "lst" in kinds:
            firsts = {}
            for it in sorted(items_for(m["lst"]["collection"], m["lst"]["item_prefix"], h, v), key=item_datetime):
                firsts.setdefault((item_datetime(it).year, item_datetime(it).month), it)
            for it in firsts.values():
                for kind, asset in m["lst"]["assets"].items():
                    jobs.append((kind, it.assets[asset].href, sub, item_datetime(it).year))
    return jobs


def extract_points(pts: pd.DataFrame, m: dict, kinds: tuple[str, ...] = ("npp", "lst")) -> pd.DataFrame:
    import pystac_client
    pts = pts.copy()
    pts["h"], pts["v"] = sinusoidal_tiles(pts.lon.values, pts.lat.values, m)
    catalog = pystac_client.Client.open(m["stac_url"])
    tokens = TokenCache(m["sas_token_url"], m["token_refresh_s"])
    jobs = plan_jobs(pts, m, catalog, kinds)
    log.info("%d points, %d tiles, %d raster reads", len(pts), pts.groupby(["h", "v"]).ngroups, len(jobs))
    acc: dict = {}
    failed = []

    def run(job):
        kind, href, sub, _yr = job
        err = None
        for attempt in range(m["retries"]):
            try:
                return kind, read_windows(href + "?" + tokens.get(), sub, kind, m), None
            except Exception as e:  # noqa: BLE001 - retried, then recorded
                err = e
                time.sleep(3 * (attempt + 1))
                if "403" in str(e):
                    tokens.get(force=True)
        return kind, {}, f"{href}: {err}"

    with ThreadPoolExecutor(m["threads"]) as ex:
        for f in as_completed([ex.submit(run, j) for j in jobs]):
            kind, vals, err = f.result()
            if err:
                failed.append(err)
            for k, val in vals.items():
                acc.setdefault((k, kind), []).append(val)
    rows = []
    all_kinds = (["npp"] if "npp" in kinds else []) + (list(m["lst"]["assets"]) if "lst" in kinds else [])
    for k in pts.site_key:
        row = {"site_key": k}
        for kind in all_kinds:
            v = np.array(acc.get((k, kind), []), float)
            row[kind] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
            row[kind + "_n"] = int(np.isfinite(v).sum())
        rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs["failed_reads"] = failed
    out.attrs["n_jobs"] = len(jobs)
    return out


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


def modis_points(cfg: Config) -> dict:
    from ..netutil import check_reachable
    m = cfg["sources"]["modis"]
    pts = modis_point_set(cfg)
    out_path = cfg.path("interim", "modis_points.parquet")
    if out_path.exists():
        prev = pd.read_parquet(out_path)
        if set(pts.site_key) <= set(prev.site_key):
            log.info("modis_points: cached values cover all %d points", len(pts))
            res = {"n_points": int(len(pts)), "cached": True}
            write_json(res, cfg.path("results", "modis_points.json"))
            return res
    check_reachable(m["stac_url"])
    check_reachable(m["sas_token_url"])
    vals = extract_points(pts, m)
    write_table(vals, out_path)
    res = {"n_points": int(len(pts)), "cached": False, "n_raster_reads": vals.attrs.get("n_jobs"),
           "n_failed_reads": len(vals.attrs.get("failed_reads", [])),
           "failed_reads_head": vals.attrs.get("failed_reads", [])[:20],
           "missing": {c: int(vals[c].isna().sum()) for c in ["npp", "lst_day", "lst_night"] if c in vals}}
    write_json(res, cfg.path("results", "modis_points.json"))
    return res
