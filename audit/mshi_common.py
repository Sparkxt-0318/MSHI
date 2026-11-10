"""mshi_common.py - shared helpers for the audit scripts numbered 20 and up.

Everything that more than one script needs lives here: paths, the SRDB reader
(with the "None" pitfall handled), quality-flag parsing, country-name
normalisation, Natural Earth point-in-polygon lookups and the continent
mapping, 0.05-degree cell ids, raster sampling, metrics, bootstrap helpers,
spatial-block folds, the XGBoost tuning grid, and figure styling.

Scripts import it with
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import mshi_common as C
and are run from the repository root with `python -I audit/NN_name.py`.
"""
from __future__ import annotations

import json
import math
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Paths and constants
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "audit" / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

SRDB_DIR = RAW / "srdb_repo"
SRDB_CSV = SRDB_DIR / "srdb-data.csv"
SRDB_STUDIES = SRDB_DIR / "srdb-studies.csv"
COSORE_DIR = RAW / "cosore_repo" / "inst" / "extdata" / "datasets"
NE_MAP_UNITS = RAW / "naturalearth" / "ne_10m_admin_0_map_units.geojson"
WC_DIR = RAW / "worldclim30s"
MODIS_DIR = RAW / "modis"

SEED = 42
N_BOOT = 2000
N_SEEDS = 20
BIO = [1, 4, 5, 6, 12, 14, 15, 17]
BIO_COLS = [f"bio{b}" for b in BIO]
RS_MIN, RS_MAX = 50.0, 4500.0
CELL_DEG = 0.05
BAD_QFLAGS = {"Q10", "Q11", "Q12", "Q13", "Q14"}
TOL_KM = 10.0           # point within this distance of the stated country counts as consistent
NEAR_BORDER_KM = 50.0   # mismatches closer than this to the stated country are "near border"
BLOCK_DEG = 5.0
N_FOLDS = 5
# 1 umol CO2 m-2 s-1 sustained for a 365-day year, in g C m-2 yr-1
UMOL_TO_GC_YR = 12.011 * 365.0 * 86400.0 / 1e6  # 378.78...

CONTINENT_ORDER = ["Asia", "North America", "Europe", "South & Central America", "Africa", "Oceania"]
CONT_ABBR = {"Asia": "AS", "North America": "NA", "Europe": "EU",
             "South & Central America": "SCA", "Africa": "AF", "Oceania": "OC", "Antarctica": "AN"}


def versions() -> dict:
    """Package versions for the log."""
    import importlib
    out = {"python": platform.python_version()}
    for m in ["numpy", "pandas", "scipy", "sklearn", "xgboost", "geopandas", "shapely",
              "pyproj", "rasterio", "matplotlib", "statsmodels", "rdata", "remotezip", "pyarrow"]:
        try:
            out[m] = importlib.import_module(m).__version__
        except Exception:  # noqa: BLE001
            out[m] = "not installed"
    try:
        import rasterio
        out["gdal"] = rasterio.__gdal_version__
    except Exception:  # noqa: BLE001
        pass
    return out


def write_json(obj, path: Path) -> None:
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        return str(o)
    path.write_text(json.dumps(obj, indent=2, default=default))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# SRDB reading and parsing
# ----------------------------------------------------------------------------
def load_srdb() -> pd.DataFrame:
    """Read srdb-data.csv so that the literal string "None" is NOT turned into NaN."""
    d = pd.read_csv(SRDB_CSV, keep_default_na=False, na_values=[""], low_memory=False)
    for c in ["Country", "Region", "Site_name", "Manipulation", "Meas_method", "Ecosystem_type",
              "Quality_flag", "Biome", "Ecosystem_state"]:
        if c in d.columns:
            d[c] = d[c].astype("string").str.strip()
            d.loc[d[c] == "", c] = pd.NA
    return d


def load_srdb_studies() -> pd.DataFrame:
    """srdb-studies.csv is Mac Roman encoded with classic-Mac CR line endings."""
    s = pd.read_csv(SRDB_STUDIES, keep_default_na=False, na_values=[""], low_memory=False,
                    encoding="mac_roman", lineterminator="\r")
    s["Study_number"] = pd.to_numeric(s["Study_number"], errors="coerce")
    return s


def parse_qflags(s) -> frozenset:
    """'Q01, Q03' / 'Q1' / 'Q03,Q10,Q16' -> frozenset({'Q01','Q03',...}); NaN -> empty set."""
    if s is None or (isinstance(s, float) and math.isnan(s)) or s is pd.NA:
        return frozenset()
    out = set()
    for tok in re.split(r"[,;\s]+", str(s).strip()):
        m = re.fullmatch(r"[Qq](\d+)", tok)
        if not m:
            continue
        n = int(m.group(1))
        out.add("Q0" if n == 0 else f"Q{n:02d}")
    return frozenset(out)


# ----------------------------------------------------------------------------
# Country normalisation (SRDB Country field -> set of acceptable Natural Earth names)
# ----------------------------------------------------------------------------
def norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^the ", "", s)
    return s


# stated (normalised) -> list of acceptable country names (any NE name field may match)
COUNTRY_ALIASES = {
    "usa": ["United States of America"], "united states": ["United States of America"],
    "u s": ["United States of America"], "us": ["United States of America"],
    "kansas": ["United States of America"], "florida": ["United States of America"],
    "uk": ["United Kingdom"], "england": ["United Kingdom"], "scotland": ["United Kingdom"],
    "wales": ["United Kingdom"], "great britain": ["United Kingdom"],
    "korea": ["South Korea"], "south korea": ["South Korea"],
    "isreal": ["Israel"], "malyasia": ["Malaysia"], "signapore": ["Singapore"],
    "new zeland": ["New Zealand"], "zamibia": ["Zambia"], "bennin": ["Benin"],
    "czech republic": ["Czechia"], "czech": ["Czechia"], "cesko": ["Czechia"],
    "czechoslovakia": ["Czechia", "Slovakia"],
    "congo": ["Republic of the Congo", "Democratic Republic of the Congo"],
    "republic of congo": ["Republic of the Congo"],
    "democratic republic of congo": ["Democratic Republic of the Congo"],
    "republic of niger": ["Niger"], "kingdom of saudi arabia": ["Saudi Arabia"],
    "tuscany": ["Italy"], "murcia": ["Spain"],
    "borneo": ["Malaysia", "Indonesia", "Brunei"],
    "micronesia": ["Federated States of Micronesia", "Guam", "Northern Mariana Islands", "Palau",
                   "Marshall Islands"],
    "sudan": ["Sudan", "South Sudan"],
    "serbia": ["Serbia", "Republic of Serbia", "Kosovo"],
    "tanzania": ["United Republic of Tanzania", "Tanzania"],
}
# region labels used in the Country field: (kind, value)
REGION_LABELS = {"europe": ("continent", "Europe"), "africa": ("continent", "Africa"),
                 "antarctica": ("continent", "Antarctica"), "arctic": ("lat_min", 60.0)}

# Natural Earth units that are themselves disputed or partially recognised: a record labelled with the
# claimant's name and located inside such a unit is a political naming difference, wherever it is
DISPUTED_UNITS = {"taiwan", "kosovo", "western sahara", "w sahara", "northern cyprus", "n cyprus",
                  "somaliland", "palestine", "siachen glacier"}

# disputed / de facto areas where a stated-vs-polygon difference is political, not an error
POLITICAL_EQUIV = [
    {"ukraine", "russia"},          # Crimea is drawn de facto in Natural Earth
    {"serbia", "republic of serbia", "kosovo"},
    {"cyprus", "northern cyprus"},
    {"somalia", "somaliland"},
    {"morocco", "western sahara"},
    {"china", "taiwan"},
    {"india", "pakistan", "china", "siachen glacier"},  # Kashmir
    {"israel", "palestine"},
]


def stated_targets(country) -> tuple[str, set]:
    """Return (kind, payload): kind 'none' (missing), 'names' (set of normalised names),
    or a region label kind ('continent'/'lat_min')."""
    if country is None or country is pd.NA or (isinstance(country, float) and math.isnan(country)):
        return ("none", set())
    k = norm_name(country)
    if k in REGION_LABELS:
        return REGION_LABELS[k]
    names = COUNTRY_ALIASES.get(k, [str(country).strip()])
    return ("names", {norm_name(n) for n in names})


# ----------------------------------------------------------------------------
# Natural Earth map units, continent mapping
# ----------------------------------------------------------------------------
NE_NAME_FIELDS = ["ADMIN", "NAME", "NAME_LONG", "GEOUNIT", "SOVEREIGNT", "BRK_NAME", "NAME_SORT",
                  "NAME_CIAWF", "FORMAL_EN", "SUBUNIT"]


def _continent_from_unit(cont: str, subregion: str) -> str:
    if subregion in ("Central America", "Caribbean") or cont == "South America":
        return "South & Central America"
    if cont == "Seven seas (open ocean)":
        return {"Eastern Africa": "Africa", "Southern Europe": "Europe",
                "Central America": "South & Central America"}.get(subregion, "Other")
    return cont


def load_map_units():
    import geopandas as gpd
    g = gpd.read_file(NE_MAP_UNITS)
    g = g[["geometry"] + [c for c in NE_NAME_FIELDS + ["CONTINENT", "SUBREGION"] if c in g.columns]].copy()
    g["unit_id"] = np.arange(len(g))
    g["continent_ne"] = [_continent_from_unit(c, s) for c, s in zip(g["CONTINENT"], g["SUBREGION"])]
    g["names_norm"] = [
        {norm_name(r[f]) for f in NE_NAME_FIELDS if f in g.columns and isinstance(r[f], str) and r[f]}
        for _, r in g.iterrows()
    ]
    g["unit_name"] = g["NAME"]
    return g


def continent_override(lat: float, lon: float, unit_name: str, cont: str) -> str:
    """Documented geographic overrides for units that span continents."""
    if unit_name == "Russia" and (lon >= 60.0 or lon < 0.0):
        return "Asia"  # Ural split (west of 60E stays Europe); lon < 0 = Chukotka east of the antimeridian
        # (no SRDB/COSORE record is affected at 02163a7; checked 2026-11-10)
    if unit_name in ("United States of America",) and 18.0 <= lat <= 23.0 and -161.0 <= lon <= -154.0:
        return "Oceania"  # Hawaii (Polynesia)
    if unit_name == "Spain" and 27.0 <= lat <= 29.6 and -18.5 <= lon <= -13.0:
        return "Africa"  # Canary Islands
    return cont


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class CountryLocator:
    """Point -> Natural Earth map unit, with distance helpers."""

    def __init__(self):
        from shapely import STRtree
        self.units = load_map_units()
        self.geoms = list(self.units.geometry.values)
        self.tree = STRtree(self.geoms)
        # name -> unit indices
        self.name_index: dict[str, list[int]] = {}
        for i, ns in enumerate(self.units["names_norm"]):
            for n in ns:
                self.name_index.setdefault(n, []).append(i)

    def unit_at(self, lat: float, lon: float):
        from shapely.geometry import Point
        p = Point(lon, lat)
        cand = self.tree.query(p, predicate="intersects")
        if len(cand) == 0:
            return None
        return int(cand[0])

    def units_at(self, lats, lons):
        import shapely
        pts = shapely.points(np.asarray(lons, float), np.asarray(lats, float))
        idx_pt, idx_geom = self.tree.query(pts, predicate="intersects")
        out = np.full(len(pts), -1, dtype=int)
        # first hit wins (map units do not overlap except along shared borders)
        seen = set()
        for a, b in zip(idx_pt, idx_geom):
            if a not in seen:
                out[a] = b
                seen.add(a)
        return out

    def dist_to_units_km(self, lat: float, lon: float, unit_ids) -> float:
        """Distance (km) from the point to the nearest of the given units.
        Step 1: the planar (lon/lat-degree) nearest point gives a real point on the polygon, so its
        haversine distance d_up is an upper bound on the true minimum. Step 2 (added after review: the
        planar nearest point is not the geodesic nearest at high latitude, e.g. 17.9 vs 9.8 km for
        Kannus, Finland): clip the polygon to a box that contains every point within d_up of the point,
        project it to an azimuthal-equidistant CRS centred on the point and take the exact distance.
        The refinement is applied only when d_up <= 300 km."""
        from shapely.geometry import Point, box
        from shapely.ops import nearest_points, transform
        import pyproj
        p = Point(lon, lat)
        best = np.inf
        tr = None
        for u in unit_ids:
            g = self.geoms[u]
            if g.intersects(p):
                return 0.0
            q = nearest_points(g, p)[0]
            d_up = float(haversine_km(lat, lon, q.y, q.x))
            d_u = d_up
            if d_up > 300.0:
                # far polygons: an equidistant projection centred on the point distorts straight edges
                # near the antipode, and every decision threshold (10/50/100 km) is far below 300 km
                best = min(best, d_u)
                continue
            dlat = d_up / 110.5 + 0.05
            coslat = math.cos(math.radians(min(abs(lat) + dlat, 89.0)))
            dlon = min(d_up / (111.3 * max(coslat, 0.02)) + 0.05, 180.0)
            clip = g.intersection(box(lon - dlon, lat - dlat, lon + dlon, lat + dlat))
            if not clip.is_empty:
                if tr is None:
                    tr = pyproj.Transformer.from_crs(
                        "EPSG:4326", f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m", always_xy=True)
                d_u = min(d_up, transform(tr.transform, clip).distance(Point(0.0, 0.0)) / 1000.0)
            best = min(best, d_u)
        return best

    def nearest_unit(self, lat: float, lon: float, max_km: float):
        """Nearest unit within max_km (approximate); returns (unit_id, km) or (None, inf)."""
        from shapely.geometry import Point
        p = Point(lon, lat)
        deg = max_km / 111.0 / max(math.cos(math.radians(min(abs(lat), 85.0))), 0.05)
        cand = self.tree.query(p.buffer(deg))
        best, best_km = None, np.inf
        for u in cand:
            km = self.dist_to_units_km(lat, lon, [int(u)])
            if km < best_km:
                best, best_km = int(u), km
        if best_km <= max_km:
            return best, best_km
        return None, np.inf

    def stated_unit_ids(self, names_norm: set) -> list[int]:
        out = []
        for n in names_norm:
            out += self.name_index.get(n, [])
        return sorted(set(out))

    def continent_of(self, lat, lon, unit_id) -> str:
        if unit_id is None or unit_id < 0:
            return "Sea"
        r = self.units.iloc[unit_id]
        return continent_override(lat, lon, r["unit_name"], r["continent_ne"])


# ----------------------------------------------------------------------------
# Grid cells and raster sampling
# ----------------------------------------------------------------------------
def cell_index(lat, lon):
    """MODIS-CMG-aligned 0.05-degree cell indices (col from -180, row from +90)."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    ix = np.floor((lon + 180.0) * 20.0 + 1e-9).astype(int).clip(0, 7199)
    iy = np.floor((90.0 - lat) * 20.0 + 1e-9).astype(int).clip(0, 3599)
    return ix, iy


def cell_center(ix, iy):
    return 90.0 - (np.asarray(iy) + 0.5) * CELL_DEG, -180.0 + (np.asarray(ix) + 0.5) * CELL_DEG


def sample_raster(path: Path, lats, lons, search_radius_px: int = 3):
    """Nearest-pixel sample; if the pixel is nodata, take the nearest valid pixel within
    +-search_radius_px (Chebyshev window, Euclidean nearest). Returns (values, offset_px)."""
    import rasterio
    from rasterio.windows import Window
    lats = np.asarray(lats, float)
    lons = np.asarray(lons, float)
    vals = np.full(len(lats), np.nan)
    off = np.full(len(lats), np.nan)
    with rasterio.open(path) as r:
        nod = r.nodata
        rows, cols = rasterio.transform.rowcol(r.transform, lons, lats)
        rows = np.asarray(rows)
        cols = np.asarray(cols)
        inside = (rows >= 0) & (cols >= 0) & (rows < r.height) & (cols < r.width)
        order = np.argsort(rows, kind="stable")
        order = order[inside[order]]
        # pass 1: centre pixels (row-sorted so GDAL's block cache is reused)
        xs = r.xy(rows[order], cols[order])
        centre = np.array([v[0] for v in r.sample(list(zip(xs[0], xs[1])))], dtype="float64")
        badc = ~np.isfinite(centre)
        if nod is not None:
            badc |= np.isclose(centre, nod) | (centre < -1e30)
        vals[order[~badc]] = centre[~badc]
        off[order[~badc]] = 0
        # pass 2: nearest valid pixel in a window, only where the centre is nodata
        for i in order[badc]:
            rr, cc = int(rows[i]), int(cols[i])
            if rr < 0 or cc < 0 or rr >= r.height or cc >= r.width:
                continue
            r0, c0 = max(rr - search_radius_px, 0), max(cc - search_radius_px, 0)
            r1, c1 = min(rr + search_radius_px + 1, r.height), min(cc + search_radius_px + 1, r.width)
            w = r.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype("float64")
            bad = ~np.isfinite(w)
            if nod is not None:
                bad |= np.isclose(w, nod) | (w < -1e30)
            ys, xs = np.nonzero(~bad)
            if len(ys) == 0:
                continue
            d = np.hypot(ys - (rr - r0), xs - (cc - c0))
            k = int(np.argmin(d))
            vals[i] = w[ys[k], xs[k]]
            off[i] = d[k]
    return vals, off


# ----------------------------------------------------------------------------
# Metrics and bootstrap
# ----------------------------------------------------------------------------
def r2(obs, pred):
    obs = np.asarray(obs, float)
    pred = np.asarray(pred, float)
    sst = np.sum((obs - obs.mean()) ** 2)
    return 1.0 - np.sum((obs - pred) ** 2) / sst


def metrics(obs_log, pred_log) -> dict:
    """R2 on the log scale (as in the original study); RMSE/MAE/bias in g C m-2 yr-1 after exp();
    bias_log on the log scale; Spearman rank correlation."""
    from scipy.stats import spearmanr
    o = np.asarray(obs_log, float)
    p = np.asarray(pred_log, float)
    eo, ep = np.exp(o), np.exp(p)
    return {
        "r2": float(r2(o, p)),
        "rmse_g": float(np.sqrt(np.mean((ep - eo) ** 2))),
        "mae_g": float(np.mean(np.abs(ep - eo))),
        "bias_g": float(np.mean(ep - eo)),
        "bias_log": float(np.mean(p - o)),
        "spearman": float(spearmanr(o, p).correlation) if np.std(p) > 0 else float("nan"),
    }


def _rank_rows(a):
    """Row-wise average ranks (ties -> average) for a 2-D array."""
    from scipy.stats import rankdata
    return rankdata(a, axis=1)


def boot_metrics(obs_log, preds_log, n_boot=N_BOOT, seed=SEED, idx=None):
    """Bootstrap test sites. preds_log: (S, n) array (S seeds; S=1 for deterministic models).
    For each resample the metric is computed per seed and averaged over seeds.
    Returns dict metric -> (point_estimate_mean_over_seeds, lo, hi, seed_sd) and the raw
    bootstrap matrix for paired differences."""
    o = np.asarray(obs_log, float)
    P = np.atleast_2d(np.asarray(preds_log, float))
    n = len(o)
    if idx is None:
        idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    ob = o[idx]                       # (B, n)
    eo = np.exp(ob)
    names = ["r2", "rmse_g", "mae_g", "bias_g", "bias_log", "spearman"]
    acc = {k: np.zeros(idx.shape[0]) for k in names}
    point = {k: [] for k in names}
    rk_o = _rank_rows(ob)
    for s in range(P.shape[0]):
        p = P[s]
        m = metrics(o, p)
        for k in names:
            point[k].append(m[k])
        pb = p[idx]
        ep = np.exp(pb)
        sst = np.sum((ob - ob.mean(axis=1, keepdims=True)) ** 2, axis=1)
        acc["r2"] += 1 - np.sum((ob - pb) ** 2, axis=1) / sst
        acc["rmse_g"] += np.sqrt(np.mean((ep - eo) ** 2, axis=1))
        acc["mae_g"] += np.mean(np.abs(ep - eo), axis=1)
        acc["bias_g"] += np.mean(ep - eo, axis=1)
        acc["bias_log"] += np.mean(pb - ob, axis=1)
        rk_p = _rank_rows(pb)
        ro = rk_o - rk_o.mean(axis=1, keepdims=True)
        rp = rk_p - rk_p.mean(axis=1, keepdims=True)
        den = np.sqrt(np.sum(ro ** 2, axis=1) * np.sum(rp ** 2, axis=1))
        with np.errstate(invalid="ignore", divide="ignore"):
            acc["spearman"] += np.where(den > 0, np.sum(ro * rp, axis=1) / den, np.nan)
    out = {}
    for k in names:
        b = acc[k] / P.shape[0]
        out[k] = {
            "est": float(np.mean(point[k])),
            "lo": float(np.nanpercentile(b, 2.5)),
            "hi": float(np.nanpercentile(b, 97.5)),
            "seed_sd": float(np.std(point[k], ddof=1)) if P.shape[0] > 1 else 0.0,
        }
        out[k + "_boot"] = b
    return out


def boot_idx(n, n_boot=N_BOOT, seed=SEED):
    return np.random.default_rng(seed).integers(0, n, size=(n_boot, n))


def cluster_boot_idx(groups, n_boot=N_BOOT, seed=SEED):
    """Resample clusters (e.g. spatial blocks or cells) with replacement; returns a list of index
    arrays (variable length)."""
    groups = np.asarray(groups)
    ug, inv = np.unique(groups, return_inverse=True)
    members = [np.nonzero(inv == g)[0] for g in range(len(ug))]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(ug), size=len(ug))
        out.append(np.concatenate([members[g] for g in pick]))
    return out


# ----------------------------------------------------------------------------
# Spatial blocks and folds
# ----------------------------------------------------------------------------
def block_id(lat, lon, deg=BLOCK_DEG):
    bx = np.floor((np.asarray(lon) + 180.0) / deg).astype(int)
    by = np.floor((np.asarray(lat) + 90.0) / deg).astype(int)
    return bx * 1000 + by


def block_folds(lat, lon, k=N_FOLDS, seed=SEED, deg=BLOCK_DEG):
    """Assign whole 5-degree blocks to k folds at random (seeded). Returns fold array."""
    b = block_id(lat, lon, deg)
    ub = np.unique(b)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(ub))
    fold_of_block = {ub[j]: (i % k) for i, j in enumerate(perm)}
    return np.array([fold_of_block[x] for x in b])


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
def ols_fit_predict(Xtr, ytr, Xte):
    Xtr = np.column_stack([np.ones(len(Xtr)), np.asarray(Xtr, float)])
    Xte = np.column_stack([np.ones(len(Xte)), np.asarray(Xte, float)])
    beta, *_ = np.linalg.lstsq(Xtr, np.asarray(ytr, float), rcond=None)
    return Xte @ beta, beta


XGB_GRID = [
    {"max_depth": md, "learning_rate": lr, "min_child_weight": mcw, "reg_lambda": lam}
    for md in (1, 2, 3, 4, 6) for lr in (0.03, 0.1) for mcw in (1, 5, 10) for lam in (1.0, 10.0)
]
# n_estimators evaluated via iteration_range from one 600-tree fit. 5-30 trees were added after review:
# for Europe the best configuration sat on the 50-tree / lr 0.03 corner and was worse than a mean-only
# model in block CV, so the grid has to contain near-constant models.
XGB_NEST = (5, 10, 20, 30, 50, 100, 150, 300, 600)
XGB_FIXED = {"subsample": 0.8, "colsample_bytree": 0.8, "objective": "reg:squarederror",
             "tree_method": "hist", "n_jobs": 1}


def xgb_model(params: dict, n_estimators: int, seed: int):
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=n_estimators, random_state=seed, **XGB_FIXED, **params)


def xgb_cv_score(X, y, folds, params, seed=SEED):
    """Pooled out-of-fold MSE for each n_estimators in XGB_NEST."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    oof = {n: np.full(len(y), np.nan) for n in XGB_NEST}
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        m = xgb_model(params, max(XGB_NEST), seed)
        m.fit(X[tr], y[tr])
        for n in XGB_NEST:
            oof[n][te] = m.predict(X[te], iteration_range=(0, n))
    return {n: float(np.mean((oof[n] - y) ** 2)) for n in XGB_NEST}


def xgb_tune(X, y, folds, n_jobs=4, seed=SEED):
    """Grid search by spatial-block CV inside the training data only. Returns best params,
    best n_estimators and the full score table."""
    from joblib import Parallel, delayed
    res = Parallel(n_jobs=n_jobs)(delayed(xgb_cv_score)(X, y, folds, p, seed) for p in XGB_GRID)
    rows = []
    for p, sc in zip(XGB_GRID, res):
        for n, mse in sc.items():
            rows.append({**p, "n_estimators": n, "cv_mse": mse})
    tab = pd.DataFrame(rows).sort_values("cv_mse").reset_index(drop=True)
    best = tab.iloc[0].to_dict()
    params = {k: best[k] for k in ["max_depth", "learning_rate", "min_child_weight", "reg_lambda"]}
    params["max_depth"] = int(params["max_depth"])
    return params, int(best["n_estimators"]), tab


def xgb_seed_predictions(Xtr, ytr, Xte_list, params, n_estimators, n_seeds=N_SEEDS, base_seed=SEED,
                         return_both=False):
    """Fit n_seeds models (seeds base_seed..base_seed+n_seeds-1); return list of (S, n_te) arrays and
    the per-feature importance, as shares summed over seeds.
    Default importance = share of TOTAL gain (XGBoost 'total_gain'), which is what R's
    xgb.importance()$Gain and hence caret/CAST (Meyer & Pebesma DI weights) use. With
    return_both=True also returns the share of AVERAGE gain per split ('gain'), the measure used in
    the first run of 25_a1_coverage.py (kept as a sensitivity)."""
    Xtr = np.asarray(Xtr, float)
    outs = [np.zeros((n_seeds, len(x))) for x in Xte_list]
    tot_imp = np.zeros(Xtr.shape[1])
    avg_imp = np.zeros(Xtr.shape[1])
    for s in range(n_seeds):
        m = xgb_model(params, n_estimators, base_seed + s)
        m.set_params(n_jobs=4)
        m.fit(Xtr, np.asarray(ytr, float))
        for j, x in enumerate(Xte_list):
            outs[j][s] = m.predict(np.asarray(x, float))
        b = m.get_booster()
        for k, v in b.get_score(importance_type="total_gain").items():
            tot_imp[int(k[1:])] += v
        for k, v in b.get_score(importance_type="gain").items():
            avg_imp[int(k[1:])] += v
    tot_share = tot_imp / tot_imp.sum() if tot_imp.sum() > 0 else tot_imp
    avg_share = avg_imp / avg_imp.sum() if avg_imp.sum() > 0 else avg_imp
    if return_both:
        return outs, tot_share, avg_share
    return outs, tot_share


# ----------------------------------------------------------------------------
# Figure style (Okabe-Ito categorical palette; cividis for sequential)
# ----------------------------------------------------------------------------
OKABE_ITO = {"black": "#000000", "orange": "#E69F00", "skyblue": "#56B4E9", "green": "#009E73",
             "yellow": "#F0E442", "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7",
             "grey": "#999999"}


def set_style():
    import matplotlib as mpl
    mpl.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.spines.top": False,
        "axes.spines.right": False, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
        "ytick.major.width": 0.6, "savefig.dpi": 300, "figure.dpi": 150, "pdf.fonttype": 42,
        "axes.titleweight": "bold",
    })
