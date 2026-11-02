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
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

from ..config import Config
from ..io import write_result, write_table
from .fetch import cosore_repo_path

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
    verify_git_checkout(cosore_repo_path(cfg), cfg["sources"]["cosore"]["commit"])   # pinned commit, unmodified
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
