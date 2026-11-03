"""COSORE v0.8.0 -> one annual Rs value per dataset (site).

Port of ``docs/handoff/scripts/cosore_aggregate.py`` (itself a copy of the repo's original
script). For each dataset: parse DESCRIPTION.txt for coordinates, read data/data.RDS with the
Python ``rdata`` parser, and integrate each port's mean flux to an annual value when the port has
>= 150 unique observation days spanning >= 180 calendar days. Qualifying ports are averaged.

Annual conversion: a flux of 1 umol CO2 m-2 s-1 sustained for a year is
12.011 * 31,536,000 / 1e6 = 378.79 g C m-2 yr-1.

Every dataset that yields no annual value is recorded in ``results/cosore_annual.json`` with the
reason: ``no_rds`` (no data file), ``parse_error`` (``rdata`` failed), ``no_qualifying_port`` (no port
meets the coverage rule) or ``unusable_content`` (no complete flux/port/timestamp rows).

``cosore_annual_analysis`` is the COSORE table for v3's own analyses (author's decision Q-6, docs/DECISIONS.md
DEV-C1-6 and D-P2-1); the reproduction keeps ``cosore_annual``. It keeps only ports that PORTS.txt describes
as soil respiration (``CSR_MSMT_VAR == "Rs"``: not Rh, NEE or Reco) and untreated (``CSR_TREATMENT ==
"None"``; a port without its own row takes the row of port 0, "all ports"), with full-year coverage: at least
``min_days_per_month`` observation days in every calendar month (pooled over years), on top of the handoff's
150 days spanning 180 days. A port's annual value is the mean of its 12 monthly means of daily means (fluxes
clipped as in the handoff), so every month weighs the same; the handoff-style mean of all observations of the
same ports is recorded next to it for comparison.
"""
from __future__ import annotations

import csv
import io
import logging
import warnings
from pathlib import Path

import pandas as pd

from ..config import Config
from ..io import write_result, write_table
from .fetch import cosore_read_paths, cosore_repo_path

log = logging.getLogger("mshi.cosore")


def parse_description(path: Path) -> dict:
    """Parse COSORE's DESCRIPTION.txt ``key: value`` file."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def read_rds(path: Path):
    import rdata  # local import: optional for stages that do not need it
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = rdata.parser.parse_file(path)
        return rdata.conversion.convert(parsed)


def integrate_ports(df: pd.DataFrame, min_days: int, min_span: int, clip: tuple[float, float],
                    factor: float) -> tuple[pd.DataFrame | None, str | None]:
    """Per-port annual flux (g C m-2 yr-1) for ports meeting the coverage rule.

    Returns (table, None) on success or (None, reason) when the dataset yields no annual value.
    """
    need = {"CSR_FLUX_CO2", "CSR_PORT", "CSR_TIMESTAMP_BEGIN"}
    if not isinstance(df, pd.DataFrame):
        return None, f"parsed object is {type(df).__name__}, not a data frame"
    missing = sorted(need - set(df.columns))
    if missing:
        return None, f"missing columns {missing}"
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    if len(df) == 0:
        return None, "no complete flux/port/timestamp rows"
    df = df.assign(t=pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce")).dropna(subset=["t"])
    if len(df) == 0:
        return None, "no parseable timestamps"
    df["day"] = df["t"].dt.normalize()
    rows = []
    for port, g in df.groupby("CSR_PORT"):
        n_days = g["day"].nunique()
        span_days = (g["day"].max() - g["day"].min()).days
        if n_days < min_days or span_days < min_span:
            continue
        mean_umol = g["CSR_FLUX_CO2"].clip(lower=clip[0], upper=clip[1]).mean()
        rows.append({"port": int(port) if pd.notna(port) else -1, "n": len(g), "n_days": int(n_days),
                     "span_days": int(span_days), "mean_umol_m2_s": float(mean_umol),
                     "rs_annual": float(mean_umol * factor)})
    if not rows:
        return None, f"no port with >= {min_days} observation days spanning >= {min_span} days"
    return pd.DataFrame(rows), None


def cosore_annual(cfg: Config) -> dict:
    p = cfg["cosore_annual"]
    factor = p["molar_mass_c"] * p["seconds_per_year"] / 1e6
    from ..netutil import verify_git_checkout
    verify_git_checkout(cosore_repo_path(cfg), cfg["sources"]["cosore"]["commit"],   # pinned commit, unmodified
                        pathspec=cosore_read_paths(cfg))
    root = cosore_repo_path(cfg) / cfg["sources"]["cosore"]["datasets_dir"]
    datasets = sorted(d for d in root.iterdir() if d.is_dir())
    rows, unreadable, bad_meta, no_port, out_of_range, test_skipped = [], [], [], [], [], []
    for ds in datasets:
        if ds.name.startswith(p["skip_prefix"]):
            test_skipped.append(ds.name)
            continue
        meta = parse_description(ds / "DESCRIPTION.txt")
        try:
            lat = float(meta.get("CSR_LATITUDE", ""))
            lon = float(meta.get("CSR_LONGITUDE", ""))
        except (TypeError, ValueError):
            bad_meta.append(ds.name)
            continue
        rds = ds / "data" / "data.RDS"
        ports, err, kind = None, None, None
        if rds.exists():
            try:
                raw = read_rds(rds)
            except Exception as e:  # noqa: BLE001 - parser failures are data, recorded below
                err, kind = f"{type(e).__name__}: {str(e)[:200]}", "parse_error"
            else:
                ports, err = integrate_ports(raw, p["min_obs_days"], p["min_span_days"],
                                             tuple(p["flux_clip_umol"]), factor)
                kind = None if ports is not None else ("no_qualifying_port" if err.startswith("no port")
                                                       else "unusable_content")
        else:
            err, kind = "data/data.RDS missing", "no_rds"
        if ports is None:
            # The handoff counted every case where integrate_dataset() returned None as "RDS unreadable";
            # keep that total (n_unreadable_or_no_data) but record the actual reason per dataset.
            unreadable.append({"dataset": ds.name, "kind": kind, "reason": err})
            continue
        rs_site = float(ports["rs_annual"].mean())
        lo, hi = p["rs_range"]
        if not (lo <= rs_site <= hi):
            out_of_range.append({"dataset": ds.name, "rs_annual": rs_site})
            continue
        rows.append({"site_id": f"cosore_{ds.name}", "source": "cosore", "longitude": lon, "latitude": lat,
                     "rs_annual": rs_site, "n_ports_qualifying": int(len(ports)),
                     "site_name": meta.get("CSR_SITE_NAME", ""), "igbp": meta.get("CSR_IGBP", ""),
                     # COSORE asks users to cite each dataset's primary publication (CC-BY-4.0 attribution)
                     "primary_publication": meta.get("CSR_PRIMARY_PUB", ""),
                     "other_publications": meta.get("CSR_OTHER_PUBS", meta.get("CSR_OTHER_PUBSs", "")),
                     "acknowledgment": meta.get("CSR_ACKNOWLEDGMENT", "")})
    out = pd.DataFrame(rows, columns=["site_id", "source", "longitude", "latitude", "rs_annual",
                                      "n_ports_qualifying", "site_name", "igbp", "primary_publication",
                                      "other_publications", "acknowledgment"])
    out_path = write_table(out, cfg.path("derived", "cosore_annual.csv"))
    res = {"n_dataset_dirs": len(datasets), "n_test_skipped": len(test_skipped),
           "n_sites": int(len(out)), "n_bad_metadata": len(bad_meta), "bad_metadata": bad_meta,
           "n_unreadable_or_no_data": len(unreadable), "unreadable_or_no_data": unreadable,
           "n_by_kind": pd.Series([u["kind"] for u in unreadable], dtype=object).value_counts().to_dict(),
           "n_out_of_rs_range": len(out_of_range), "out_of_rs_range": out_of_range,
           "igbp_counts": out["igbp"].value_counts().to_dict(),
           "rs_annual_summary": out["rs_annual"].describe().round(2).to_dict() if len(out) else {},
           "rule": {"min_obs_days": p["min_obs_days"], "min_span_days": p["min_span_days"],
                    "flux_clip_umol": p["flux_clip_umol"], "factor_gC_per_umol": factor}}
    write_result(cfg, res, "cosore_annual.json", outputs=[out_path])
    log.info("COSORE: %d sites, %d datasets unreadable/no data", len(out), len(unreadable))
    return res


def parse_ports(path: Path) -> dict[int, dict]:
    """COSORE's PORTS.txt as {port: row}. The files are comma-separated with ``#`` comment lines and tab
    padding before (sometimes quoted) fields; tabs are turned into spaces first so that quoted fields with
    commas parse, and short rows are padded with empty fields."""
    if not path.exists():
        return {}
    lines = [ln.replace("\t", " ") for ln in path.read_text(errors="replace").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return {}
    rows = [[c.strip().strip('"').strip() for c in r] for r in csv.reader(io.StringIO("\n".join(lines)),
                                                                           skipinitialspace=True)]
    hdr = rows[0]
    recs = [dict(zip(hdr, r + [""] * (len(hdr) - len(r)))) for r in rows[1:]]
    return {int(r["CSR_PORT"]): r for r in recs if r.get("CSR_PORT", "").lstrip("-").isdigit()}


def port_annuals(df: pd.DataFrame, ports: dict[int, dict], p: dict, factor: float) -> tuple[pd.DataFrame, str | None]:
    """Per-port decisions and annual values under the analysis rule (module docstring). Returns (table of every
    port with its metadata, coverage and ``kept`` flag, None) or (empty, reason) if the data are unusable."""
    need = {"CSR_FLUX_CO2", "CSR_PORT", "CSR_TIMESTAMP_BEGIN"}
    if not isinstance(df, pd.DataFrame) or need - set(df.columns):
        return pd.DataFrame(), "unusable_content"
    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    df = df.assign(t=pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce")).dropna(subset=["t"])
    if len(df) == 0:
        return pd.DataFrame(), "unusable_content"
    df["day"] = df["t"].dt.normalize()
    lo, hi = p["flux_clip_umol"]
    rows = []
    for port, g in df.groupby("CSR_PORT"):
        meta = ports.get(int(port), ports.get(0))
        days = g["day"].drop_duplicates()
        per_month = days.dt.month.value_counts().reindex(range(1, 13), fill_value=0)
        fc = g["CSR_FLUX_CO2"].clip(lower=lo, upper=hi)
        daily = fc.groupby(g["day"]).mean()
        monthly = daily.groupby(daily.index.month).mean()
        row = {"port": int(port), "meta_port": None if meta is None else int(meta["CSR_PORT"]),
               "msmt_var": None if meta is None else meta.get("CSR_MSMT_VAR"),
               "treatment": None if meta is None else meta.get("CSR_TREATMENT"),
               "n": int(len(g)), "n_days": int(days.size), "span_days": int((days.max() - days.min()).days),
               "min_days_in_a_month": int(per_month.min()),
               "rs_annual": float(monthly.mean() * factor) if len(monthly) == 12 else None,
               "rs_annual_obs_mean": float(fc.mean() * factor)}
        why = []
        if meta is None:
            why.append("no PORTS.txt row")
        else:
            if row["msmt_var"] != p["msmt_var"]:
                why.append(f"CSR_MSMT_VAR {row['msmt_var']}")
            if row["treatment"] != p["treatment"]:
                why.append(f"treated ({row['treatment']})")
        if row["n_days"] < p["min_obs_days"] or row["span_days"] < p["min_span_days"]:
            why.append("short record")
        if row["min_days_in_a_month"] < p["min_days_per_month"]:
            why.append("not full-year")
        row["kept"], row["why_not"] = not why, "; ".join(why)
        rows.append(row)
    return pd.DataFrame(rows), None


def cosore_annual_analysis(cfg: Config) -> dict:
    """COSORE table for v3 analyses (module docstring; DEV-C1-6, D-P2-1)."""
    p = cfg["cosore_analysis"]
    factor = p["molar_mass_c"] * p["seconds_per_year"] / 1e6
    from ..netutil import verify_git_checkout
    verify_git_checkout(cosore_repo_path(cfg), cfg["sources"]["cosore"]["commit"], pathspec=cosore_read_paths(cfg))
    root = cosore_repo_path(cfg) / cfg["sources"]["cosore"]["datasets_dir"]
    rows, dropped, port_rows = [], [], []
    for ds in sorted(d for d in root.iterdir() if d.is_dir()):
        if ds.name.startswith(cfg["cosore_annual"]["skip_prefix"]):
            continue
        meta = parse_description(ds / "DESCRIPTION.txt")
        try:
            lat, lon = float(meta.get("CSR_LATITUDE", "")), float(meta.get("CSR_LONGITUDE", ""))
        except (TypeError, ValueError):
            dropped.append({"dataset": ds.name, "reason": "bad_metadata"})
            continue
        rds = ds / "data" / "data.RDS"
        if not rds.exists():
            dropped.append({"dataset": ds.name, "reason": "no_rds"})
            continue
        try:
            raw = read_rds(rds)
        except Exception as e:  # noqa: BLE001 - parser failures are data, recorded below
            dropped.append({"dataset": ds.name, "reason": "parse_error", "detail": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        ports, err = port_annuals(raw, parse_ports(ds / "PORTS.txt"), p, factor)
        if err:
            dropped.append({"dataset": ds.name, "reason": err})
            continue
        port_rows += [{"dataset": ds.name, **r} for r in ports.to_dict(orient="records")]
        kept = ports[ports.kept]
        if kept.empty:
            reasons = sorted({w for s in ports.why_not for w in s.split("; ") if w})
            dropped.append({"dataset": ds.name, "reason": "no_port_kept", "detail": reasons})
            continue
        rs_site = float(kept.rs_annual.mean())
        lo, hi = p["rs_range"]
        if not (lo <= rs_site <= hi):
            dropped.append({"dataset": ds.name, "reason": "out_of_rs_range", "rs_annual": rs_site})
            continue
        rows.append({"site_id": f"cosore_{ds.name}", "source": "cosore", "longitude": lon, "latitude": lat,
                     "rs_annual": rs_site, "rs_annual_obs_mean": float(kept.rs_annual_obs_mean.mean()),
                     "n_ports_qualifying": int(len(kept)), "n_ports_total": int(len(ports)),
                     "site_name": meta.get("CSR_SITE_NAME", ""), "igbp": meta.get("CSR_IGBP", ""),
                     "primary_publication": meta.get("CSR_PRIMARY_PUB", ""),
                     "other_publications": meta.get("CSR_OTHER_PUBS", meta.get("CSR_OTHER_PUBSs", "")),
                     "acknowledgment": meta.get("CSR_ACKNOWLEDGMENT", "")})
    cols = ["site_id", "source", "longitude", "latitude", "rs_annual", "rs_annual_obs_mean", "n_ports_qualifying",
            "n_ports_total", "site_name", "igbp", "primary_publication", "other_publications", "acknowledgment"]
    out = pd.DataFrame(rows, columns=cols)
    out_path = write_table(out, cfg.path("derived", "cosore_annual_analysis.csv"))
    pr = pd.DataFrame(port_rows)
    reasons = pd.Series([w for s in pr.why_not for w in s.split("; ") if w], dtype=object) if len(pr) else pd.Series([], dtype=object)
    res = {"exploratory": True, "rule": {k: p[k] for k in ("msmt_var", "treatment", "min_obs_days", "min_span_days",
                                                         "min_days_per_month", "flux_clip_umol", "rs_range")},
           "annual": "mean of the 12 monthly means of daily means (clipped fluxes)",
           "n_sites": int(len(out)), "n_dropped": len(dropped), "dropped": dropped,
           "n_ports_seen": int(len(pr)), "n_ports_kept": int(pr.kept.sum()) if len(pr) else 0,
           "port_exclusions": reasons.value_counts().to_dict(),
           "ports_kept_by_var": pr[pr.kept].msmt_var.value_counts().to_dict() if len(pr) else {},
           "obs_mean_over_month_balanced": (out.rs_annual_obs_mean / out.rs_annual).describe().round(3).to_dict()
           if len(out) else {},
           "ports": port_rows}
    write_result(cfg, res, "cosore_annual_analysis.json", outputs=[out_path])
    log.info("COSORE (analysis rule): %d sites, %d of %d ports kept", len(out), res["n_ports_kept"], res["n_ports_seen"])
    return {k: v for k, v in res.items() if k != "ports"}

