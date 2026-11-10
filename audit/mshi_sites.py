"""mshi_sites.py - Step 0 building blocks shared by 23_build_site_table.py (main table) and
28_a3_effect.py (re-runs with flagged records as-is / corrected).

  srdb_records(policy)   SRDB filters with removal counts; policy for country-mismatch records:
                         'exclude' (Step 0 default), 'asis' (keep original coordinates),
                         'corrected' (apply high/medium-confidence fixes, drop the rest)
  cosore_records()       COSORE dataset-year records from 21_cosore_annual.py
  add_continent(df)      Natural Earth continent at the record coordinates (+ overrides)
  add_worldclim(df)      8 bioclim layers at 30", nearest valid pixel within 3 px, cached
  aggregate_sites(df)    one row per 0.05-degree cell: mean log Rs, n records, within-cell SD
  add_npp(sites)         MODIS NPP 2020-2024 mean at the cell centre (tifffile reader)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

CACHE = C.OUT / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

IGBP_TO_ECO = {"Evergreen needleleaf forest": "Forest", "Evergreen broadleaf forest": "Forest",
               "Deciduous needleleaf forest": "Forest", "Deciduous broadleaf forest": "Forest",
               "Mixed forests": "Forest", "Mixed forest": "Forest", "Closed shrubland": "Shrubland",
               "Open shrubland": "Shrubland", "Woody savanna": "Savanna", "Savannas": "Savanna",
               "Savanna": "Savanna", "Grassland": "Grassland", "Grasslands": "Grassland",
               "Wetland": "Wetland", "Permanent wetlands": "Wetland", "Cropland": "Agriculture",
               "Croplands": "Agriculture", "Urban": "Urban"}


def _step(steps, rule, before, after, note=""):
    steps.append({"rule": rule, "n_before": int(before), "n_removed": int(before - after),
                  "n_after": int(after), "note": note})


def srdb_records(policy: str = "exclude", fix_conf=("high", "medium")):
    """Return (records DataFrame, steps list, marginal dict)."""
    d = C.load_srdb()
    chk = pd.read_csv(C.OUT / "srdb_country_check.csv")
    chk = chk.set_index("Record_number")
    d["qset"] = d["Quality_flag"].map(C.parse_qflags)
    steps = []
    n = len(d)
    _step(steps, "all SRDB records (srdb-data.csv @02163a7)", n, n)

    m_rs = d["Rs_annual"].notna()
    m_manip = d["Manipulation"].isna() | (d["Manipulation"] == "None")
    m_xy = d["Latitude"].notna() & d["Longitude"].notna() & (d["Latitude"].abs() <= 90) & (d["Longitude"].abs() <= 180)
    m_range = d["Rs_annual"].between(C.RS_MIN, C.RS_MAX)
    m_q = ~d["qset"].map(lambda s: bool(s & C.BAD_QFLAGS))
    m_dup = d["Duplicate_record"].isna()
    m_cov = d["Annual_coverage"].isna() | (d["Annual_coverage"] >= 1.0)
    status = d["Record_number"].map(chk["status"])
    m_ctry = status.ne("mismatch") | status.isna()

    # marginal: among records with Rs_annual, how many fail each rule on its own
    base = m_rs
    marginal = {
        "manipulated (Manipulation not 'None' or missing)": int((base & ~m_manip).sum()),
        "no/invalid coordinates": int((base & ~m_xy).sum()),
        "Rs_annual outside 50-4500": int((base & ~m_range).sum()),
        "quality flag Q10-Q14": int((base & ~m_q).sum()),
        "known duplicate (Duplicate_record set)": int((base & ~m_dup).sum()),
        "annual coverage < 1": int((base & d["Annual_coverage"].lt(1.0)).sum()),
        "annual coverage missing": int((base & d["Annual_coverage"].isna()).sum()),
        "country/coordinate mismatch": int((base & ~m_ctry).sum()),
    }
    keep = pd.Series(True, index=d.index)
    for rule, m in [("Rs_annual reported", m_rs),
                    ("unmanipulated (Manipulation == 'None' or missing)", m_manip),
                    ("coordinates present and in bounds", m_xy),
                    ("Rs_annual within 50-4500 g C m-2 yr-1", m_range),
                    ("no quality flag Q10-Q14", m_q),
                    ("not a known duplicate (Duplicate_record empty)", m_dup),
                    ("annual coverage >= 1 or missing", m_cov)]:
        before = keep.sum()
        keep &= m
        _step(steps, rule, before, keep.sum())
    x = d[keep].copy()
    x["check_status"] = x["Record_number"].map(chk["status"])
    x["check_class"] = x["Record_number"].map(chk["mismatch_class"])
    x["check_conf"] = x["Record_number"].map(chk["confidence"])
    x["lat"] = x["Latitude"].astype(float)
    x["lon"] = x["Longitude"].astype(float)
    mis = x["check_status"].eq("mismatch")
    before = len(x)
    if policy == "exclude":
        x = x[~mis]
        _step(steps, "country field agrees with coordinates (flagged records excluded)", before, len(x))
    elif policy == "asis":
        _step(steps, "country/coordinate mismatches KEPT with original coordinates", before, len(x))
    elif policy == "corrected":
        fx = x["Record_number"].map(chk["fix_lat"]), x["Record_number"].map(chk["fix_lon"])
        fixable = mis & x["check_conf"].isin(fix_conf) & fx[0].notna()
        x.loc[fixable, "lat"] = fx[0][fixable]
        x.loc[fixable, "lon"] = fx[1][fixable]
        x = x[~mis | fixable]
        _step(steps, f"mismatches with a {'/'.join(fix_conf)}-confidence fix corrected, others excluded",
              before, len(x), note=f"{int(fixable.sum())} records corrected")
    else:
        raise ValueError(policy)

    out = pd.DataFrame({
        "record_id": "srdb_" + x["Record_number"].astype(int).astype(str),
        "source": "srdb",
        "study_id": "srdb_" + x["Study_number"].astype(int).astype(str),
        "record_number": x["Record_number"].astype(int),
        "study_number": x["Study_number"].astype(int),
        "year": x["Study_midyear"].astype(float),
        "years_of_data": x["YearsOfData"].astype(float),
        "lat": x["lat"], "lon": x["lon"],
        "rs_annual": x["Rs_annual"].astype(float),
        "annual_coverage": x["Annual_coverage"].astype(float),
        "meas_method": x["Meas_method"].astype("string"),
        "ecosystem": x["Ecosystem_type"].astype("string"),
        "country_stated": x["Country"].astype("string"),
        "quality_flag": x["Quality_flag"].astype("string"),
        "check_status": x["check_status"], "check_class": x["check_class"], "check_conf": x["check_conf"],
        "site_name": x["Site_name"].astype("string"),
    })
    out["cov_missing"] = out["annual_coverage"].isna()
    out["log_rs"] = np.log(out["rs_annual"])
    return out.reset_index(drop=True), steps, marginal


def cosore_records():
    c = pd.read_csv(C.OUT / "cosore_records.csv")
    steps = []
    n = len(c)
    _step(steps, "COSORE full-year dataset-year records (Rs ports, treatment None)", n, n)
    m = c["rs_annual"].between(C.RS_MIN, C.RS_MAX) & c["latitude"].notna() & c["longitude"].notna()
    c = c[m]
    _step(steps, "Rs_annual within 50-4500 and coordinates present", n, len(c))
    out = pd.DataFrame({
        "record_id": c["record_id"], "source": "cosore", "study_id": c["study_id"],
        "record_number": np.nan, "study_number": np.nan,
        "year": c["year"].astype(float) + 0.5, "years_of_data": 1.0,
        "lat": c["latitude"].astype(float), "lon": c["longitude"].astype(float),
        "rs_annual": c["rs_annual"].astype(float), "annual_coverage": 1.0,
        "meas_method": "IRGA", "ecosystem": c["igbp"].map(IGBP_TO_ECO).astype("string"),
        "country_stated": pd.NA, "quality_flag": pd.NA, "check_status": "no_country_field",
        "check_class": pd.NA, "check_conf": pd.NA, "site_name": c["site_name"].astype("string"),
    })
    out["cov_missing"] = False
    out["log_rs"] = np.log(out["rs_annual"])
    return out.reset_index(drop=True), steps


_LOC = None


def locator():
    global _LOC
    if _LOC is None:
        _LOC = C.CountryLocator()
    return _LOC


def add_continent(df: pd.DataFrame) -> pd.DataFrame:
    loc = locator()
    u = loc.units_at(df["lat"].values, df["lon"].values)
    cont = []
    for la, lo, ui in zip(df["lat"].values, df["lon"].values, u):
        if ui < 0:
            nu, _ = loc.nearest_unit(la, lo, C.TOL_KM)
            ui = -1 if nu is None else nu
        cont.append(loc.continent_of(la, lo, ui if ui >= 0 else None))
    df = df.copy()
    df["continent"] = cont
    return df


def add_worldclim(df: pd.DataFrame) -> pd.DataFrame:
    cache_f = CACHE / "worldclim_points.parquet"
    pts = df[["lat", "lon"]].round(6).drop_duplicates()
    cache = pd.read_parquet(cache_f) if cache_f.exists() else pd.DataFrame(columns=["lat", "lon"])
    todo = pts.merge(cache[["lat", "lon"]], on=["lat", "lon"], how="left", indicator=True)
    todo = todo[todo["_merge"] == "left_only"][["lat", "lon"]]
    if len(todo):
        new = todo.copy()
        for b in C.BIO:
            v, off = C.sample_raster(C.WC_DIR / f"wc2.1_30s_bio_{b}.tif", new["lat"].values, new["lon"].values)
            new[f"bio{b}"] = v
            new[f"bio{b}_offset_px"] = off
        cache = pd.concat([cache, new], ignore_index=True) if len(cache) else new
        cache.to_parquet(cache_f, index=False)
    df = df.copy()
    df["_lat"], df["_lon"] = df["lat"].round(6), df["lon"].round(6)
    cols = ["lat", "lon"] + C.BIO_COLS + [f"bio{b}_offset_px" for b in C.BIO]
    m = df.merge(cache[cols].rename(columns={"lat": "_lat", "lon": "_lon"}), on=["_lat", "_lon"], how="left")
    return m.drop(columns=["_lat", "_lon"])


def _mode(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return pd.NA
    return s.value_counts().index[0]


def aggregate_sites(rec: pd.DataFrame) -> pd.DataFrame:
    rec = rec.copy()
    ix, iy = C.cell_index(rec["lat"].values, rec["lon"].values)
    rec["cell"] = ix.astype(np.int64) * 10000 + iy
    rec["ix"], rec["iy"] = ix, iy
    g = rec.groupby("cell", sort=True)
    sites = g.agg(
        n_records=("log_rs", "size"), log_rs=("log_rs", "mean"),
        sd_log_rs=("log_rs", lambda v: float(np.std(v, ddof=1)) if len(v) > 1 else np.nan),
        n_studies=("study_id", "nunique"), n_years=("year", "nunique"),
        year_min=("year", "min"), year_max=("year", "max"),
        sources=("source", lambda v: "+".join(sorted(set(v)))),
        n_cov_missing=("cov_missing", "sum"),
        ix=("ix", "first"), iy=("iy", "first"),
    ).reset_index()
    sites["continent"] = g["continent"].agg(_mode).values
    sites["n_continents_in_cell"] = g["continent"].nunique().values
    sites["meas_method"] = g["meas_method"].agg(_mode).values
    sites["meas_methods"] = g["meas_method"].agg(lambda v: "|".join(sorted(set(v.dropna().astype(str))))).values
    sites["ecosystem"] = g["ecosystem"].agg(_mode).values
    sites["country_stated"] = g["country_stated"].agg(_mode).values
    sites["record_ids"] = g["record_id"].agg(lambda v: ";".join(v)).values
    # location and climate: mean over the unique record locations in the cell
    locs = rec.drop_duplicates(["cell", "lat", "lon"])
    lg = locs.groupby("cell")
    sites = sites.merge(lg[["lat", "lon"] + C.BIO_COLS].mean().reset_index(), on="cell", how="left")
    sites["n_locations"] = lg.size().reindex(sites["cell"]).values
    clat, clon = C.cell_center(sites["ix"].values, sites["iy"].values)
    sites["cell_lat"], sites["cell_lon"] = clat, clon
    sites["rs_annual_gm"] = np.exp(sites["log_rs"])
    sites["log_bio12"] = np.log(np.clip(sites["bio12"], 1.0, None))
    sites["block5"] = C.block_id(sites["lat"].values, sites["lon"].values)
    return sites


_NPP = None


def _npp_array():
    global _NPP
    if _NPP is None:
        import tifffile
        with tifffile.TiffFile(C.MODIS_DIR / "npp_2020_2024_mean.tif") as t:
            p = t.pages[0]
            a = p.asarray()
            sx, sy, _ = p.tags["ModelPixelScaleTag"].value
            tp = p.tags["ModelTiepointTag"].value
            _NPP = (a, float(tp[3]), float(tp[4]), float(sx), float(sy))
    return _NPP


def add_npp(sites: pd.DataFrame, lat_col="cell_lat", lon_col="cell_lon") -> pd.DataFrame:
    """MODIS NPP 2020-2024 mean (raw units of the GEE export; MOD17 scaling suggests 0.1 g C m-2 yr-1).
    Raster covers lon -125..180, lat -39.2..87.8 only; outside -> NaN. A NaN pixel is replaced by the
    median of the finite pixels in its 3x3 neighbourhood (NaN if none)."""
    a, x0, y0, sx, sy = _npp_array()
    lat = sites[lat_col].values
    lon = sites[lon_col].values
    col = np.floor((lon - x0) / sx).astype(int)
    row = np.floor((y0 - lat) / sy).astype(int)
    vals = np.full(len(sites), np.nan)
    for i, (r, c) in enumerate(zip(row, col)):
        if 0 <= r < a.shape[0] and 0 <= c < a.shape[1]:
            v = a[r, c]
            if not np.isfinite(v):
                w = a[max(r - 1, 0): r + 2, max(c - 1, 0): c + 2]
                fin = w[np.isfinite(w)]
                v = float(np.median(fin)) if fin.size else np.nan
            vals[i] = v
    out = sites.copy()
    out["npp"] = vals
    return out
