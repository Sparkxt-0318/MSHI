"""21_cosore_annual.py - annual soil respiration records from COSORE (package version 0.8.0,
git HEAD 02f32e8; there is no v0.8.0 git tag, the version string is in DESCRIPTION).

Changes relative to scripts/cosore_aggregate.py (which averaged every port of every dataset
over its whole record, and needed only 150 observation days):
  * only ports with CSR_MSMT_VAR == "Rs" and CSR_TREATMENT == "None" (unmanipulated total Rs);
    the old script also kept trenched (Rh), girdled, warmed, irrigated, NEE and Reco ports;
  * one record per dataset x calendar year (UTC), the COSORE analogue of an SRDB record;
  * a port-year counts only if all 12 months have >= 5 days with data (annual coverage = 1);
    annual flux = day-weighted mean of the 12 monthly means of daily means;
  * flux values outside [-2, 50] umol m-2 s-1 are dropped (not clipped);
  * paths are arguments, not hard-coded.

Usage: python -I audit/21_cosore_annual.py
Outputs: audit/outputs/cosore_port_years.csv, audit/outputs/cosore_records.csv,
         audit/outputs/cosore_annual_log.json
"""
from __future__ import annotations

import calendar
import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

warnings.filterwarnings("ignore")
import rdata  # noqa: E402

MIN_DAYS_PER_MONTH = 5
FLUX_LO, FLUX_HI = -2.0, 50.0


def parse_kv(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, _, v = s.partition(":")
        out[k.strip()] = v.strip()
    return out


def parse_ports(path: Path) -> pd.DataFrame:
    lines = [l for l in path.read_text(errors="replace").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    rows = list(csv.reader(lines, skipinitialspace=True))
    hdr = [h.strip().strip('"') for h in rows[0]]
    recs = []
    for r in rows[1:]:
        r = [x.strip().strip('"').strip() for x in r]
        r += [""] * (len(hdr) - len(r))
        recs.append(dict(zip(hdr, r[: len(hdr)])))
    df = pd.DataFrame(recs)
    df["CSR_PORT"] = pd.to_numeric(df["CSR_PORT"], errors="coerce")
    return df


def port_years(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    df = df[(df["CSR_FLUX_CO2"] >= FLUX_LO) & (df["CSR_FLUX_CO2"] <= FLUX_HI)]
    if df.empty:
        return pd.DataFrame()
    t = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", utc=True, errors="coerce")
    df = df.assign(day=t.dt.floor("D")).dropna(subset=["day"])
    daily = df.groupby(["CSR_PORT", "day"], observed=True)["CSR_FLUX_CO2"].mean().reset_index()
    daily["year"] = daily["day"].dt.year
    daily["month"] = daily["day"].dt.month
    monthly = daily.groupby(["CSR_PORT", "year", "month"])["CSR_FLUX_CO2"].agg(["mean", "size"]).reset_index()
    out = []
    for (port, yr), g in monthly.groupby(["CSR_PORT", "year"]):
        good = g[g["size"] >= MIN_DAYS_PER_MONTH]
        months_ok = int(good["month"].nunique())
        rec = {"port": int(port), "year": int(yr), "months_with_data": int(g["month"].nunique()),
               "months_ok": months_ok, "n_days": int(g["size"].sum())}
        if months_ok == 12:
            ndays = np.array([calendar.monthrange(int(yr), int(m))[1] for m in good["month"]])
            mean_flux = float(np.sum(good["mean"].values * ndays) / ndays.sum())
            secs = ndays.sum() * 86400.0
            rec["mean_flux_umol"] = mean_flux
            rec["rs_annual"] = mean_flux * 12.011 * secs / 1e6
            rec["full_year"] = True
        else:
            rec["mean_flux_umol"] = float(np.average(g["mean"], weights=g["size"]))
            rec["rs_annual"] = np.nan
            rec["full_year"] = False
        out.append(rec)
    return pd.DataFrame(out)


def main() -> int:
    log = {"started": C.now_utc(), "cosore_dir": str(C.COSORE_DIR), "datasets": {}}
    all_py, recs = [], []
    for d in sorted(C.COSORE_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("TEST"):
            continue
        entry = {}
        meta = parse_kv(d / "DESCRIPTION.txt")
        try:
            lat, lon = float(meta.get("CSR_LATITUDE", "")), float(meta.get("CSR_LONGITUDE", ""))
        except ValueError:
            entry["status"] = "bad_coordinates"
            log["datasets"][d.name] = entry
            continue
        rds = d / "data" / "data.RDS"
        if not rds.exists():
            entry["status"] = "no_data_rds"
            log["datasets"][d.name] = entry
            continue
        try:
            df = rdata.read_rds(rds)
        except Exception as e:  # noqa: BLE001
            entry["status"] = f"rds_unreadable: {type(e).__name__}"
            log["datasets"][d.name] = entry
            continue
        if "CSR_FLUX_CO2" not in df.columns or "CSR_TIMESTAMP_BEGIN" not in df.columns:
            entry["status"] = "missing_columns"
            log["datasets"][d.name] = entry
            continue
        if "CSR_PORT" not in df.columns:
            df["CSR_PORT"] = 0
        ports = parse_ports(d / "PORTS.txt")
        ports["var"] = ports["CSR_MSMT_VAR"].str.strip()
        ports["trt"] = ports["CSR_TREATMENT"].str.strip()
        data_ports = sorted(pd.Series(df["CSR_PORT"]).dropna().astype(int).unique().tolist())
        if (ports["CSR_PORT"] == 0).any() and len(ports) == 1:
            pmap = {p: (ports.iloc[0]["var"], ports.iloc[0]["trt"]) for p in data_ports}
        else:
            pmap = {int(r.CSR_PORT): (r["var"], r["trt"]) for _, r in ports.iterrows() if pd.notna(r.CSR_PORT)}
            if 0 in pmap and data_ports == [0]:
                pass
        keep = [p for p in data_ports if pmap.get(p, ("?", "?")) == ("Rs", "None")]
        entry["ports_in_data"] = len(data_ports)
        entry["ports_rs_untreated"] = len(keep)
        entry["port_types"] = sorted({f"{v}|{t}" for v, t in pmap.values()})
        if not keep:
            entry["status"] = "no_untreated_rs_port"
            log["datasets"][d.name] = entry
            continue
        df = df[df["CSR_PORT"].astype("Int64").isin(keep)]
        py = port_years(df)
        if py.empty:
            entry["status"] = "no_valid_flux"
            log["datasets"][d.name] = entry
            continue
        py.insert(0, "dataset", d.name)
        all_py.append(py)
        full = py[py["full_year"]]
        entry["port_years"] = int(len(py))
        entry["port_years_full"] = int(len(full))
        if full.empty:
            entry["status"] = "no_full_year"
            log["datasets"][d.name] = entry
            continue
        for yr, g in full.groupby("year"):
            recs.append({
                "record_id": f"cosore_{d.name}_{yr}", "source": "cosore", "study_id": f"cosore_{d.name}",
                "dataset": d.name, "site_name": meta.get("CSR_SITE_NAME", ""), "latitude": lat,
                "longitude": lon, "year": int(yr), "rs_annual": float(g["rs_annual"].mean()),
                "n_ports": int(len(g)), "port_sd_log": float(np.log(g["rs_annual"].clip(lower=1e-6)).std(ddof=1))
                if len(g) > 1 else np.nan, "igbp": meta.get("CSR_IGBP", ""),
                "instrument": meta.get("CSR_INSTRUMENT", ""), "meas_method": "IRGA",
            })
        entry["status"] = "ok"
        entry["records"] = int(full["year"].nunique())
        log["datasets"][d.name] = entry

    py_all = pd.concat(all_py, ignore_index=True) if all_py else pd.DataFrame()
    rec = pd.DataFrame(recs)
    py_all.to_csv(C.OUT / "cosore_port_years.csv", index=False)
    rec.to_csv(C.OUT / "cosore_records.csv", index=False)
    st = pd.Series({k: v["status"] for k, v in log["datasets"].items()})
    log["status_counts"] = st.value_counts().to_dict()
    log["n_records_full_year"] = int(len(rec))
    log["n_datasets_with_records"] = int(rec["dataset"].nunique()) if len(rec) else 0
    log["versions"] = C.versions()
    C.write_json(log, C.OUT / "cosore_annual_log.json")
    print("dataset status:", log["status_counts"])
    print("full-year dataset-year records:", len(rec), "from", log["n_datasets_with_records"], "datasets")
    if len(rec):
        print(rec[["rs_annual"]].describe().T.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
