"""COSORE loader: walk inst/extdata/datasets/, read each dataset's
DESCRIPTION.txt and data/data.RDS, integrate per-port flux to annual Rs,
average to one row per site.

Output schema matches the SRDB rows produced by build_target.py:
    site_id, source, longitude, latitude, rs_annual

Annual conversion: a flux in μmol CO2 m-2 s-1 sustained for one year =
(flux) × 12.011 × 31,536,000 / 1e6 = (flux) × 378.79 g C m-2 yr-1.

We require at least 150 unique observation days spanning ≥180 calendar
days per port to count it as an annual integral. Sites with multiple
qualifying ports are averaged. Multi-year sites are also averaged.
"""
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="rdata")

import rdata  # noqa: E402

COSORE_ROOT = Path("/tmp/cosore/inst/extdata/datasets")
OUT_DIR = Path("/home/user/MSHI/data/raw/cosore")
OUT_DIR.mkdir(parents=True, exist_ok=True)

UMOL_CO2_PER_M2_S__TO__GC_PER_M2_YR = 12.011 * 31_536_000.0 / 1_000_000.0  # 378.79


def parse_description(path: Path) -> dict:
    """Parse the COSORE DESCRIPTION.txt key-value file."""
    out = {}
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


def integrate_dataset(rds_path: Path) -> pd.DataFrame | None:
    """Read a data.RDS and return per-port annual flux (gC m-2 yr-1)."""
    try:
        parsed = rdata.parser.parse_file(rds_path)
        df = rdata.conversion.convert(parsed)
    except Exception as e:
        return None
    if not isinstance(df, pd.DataFrame) or "CSR_FLUX_CO2" not in df.columns:
        return None
    if "CSR_PORT" not in df.columns or "CSR_TIMESTAMP_BEGIN" not in df.columns:
        return None

    df = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna()
    if len(df) == 0:
        return None

    df["t"] = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce")
    df = df.dropna(subset=["t"])
    if len(df) == 0:
        return None
    df["day"] = df["t"].dt.normalize()

    rows = []
    for port, g in df.groupby("CSR_PORT"):
        n = len(g)
        n_days = g["day"].nunique()
        span_days = (g["day"].max() - g["day"].min()).days
        if n_days < 150 or span_days < 180:
            continue
        # Filter physically implausible fluxes; CO2 efflux from soil is ~0.5–20
        # μmol m-2 s-1 typically. Be generous: keep [-2, 50].
        flux = g["CSR_FLUX_CO2"].clip(lower=-2.0, upper=50.0)
        mean_umol = flux.mean()
        rs_annual = mean_umol * UMOL_CO2_PER_M2_S__TO__GC_PER_M2_YR
        rows.append({
            "port": int(port) if pd.notna(port) else -1,
            "n": n, "n_days": n_days, "span_days": span_days,
            "mean_umol_m2_s": float(mean_umol),
            "rs_annual": float(rs_annual),
        })
    if not rows:
        return None
    return pd.DataFrame(rows)


def main() -> int:
    if not COSORE_ROOT.exists():
        print(f"COSORE root not found: {COSORE_ROOT}")
        return 1

    datasets = sorted([d for d in COSORE_ROOT.iterdir() if d.is_dir()])
    print(f"Scanning {len(datasets)} COSORE datasets...")

    site_rows = []
    n_ok = n_skip_meta = n_skip_data = n_no_qual_port = 0
    for ds in datasets:
        if ds.name.startswith("TEST"):
            continue
        meta = parse_description(ds / "DESCRIPTION.txt")
        try:
            lat = float(meta.get("CSR_LATITUDE", ""))
            lon = float(meta.get("CSR_LONGITUDE", ""))
        except (TypeError, ValueError):
            n_skip_meta += 1
            continue

        rds = ds / "data" / "data.RDS"
        ports = integrate_dataset(rds) if rds.exists() else None
        if ports is None:
            n_skip_data += 1
            continue
        if len(ports) == 0:
            n_no_qual_port += 1
            continue

        # Average across all qualifying ports for this site
        rs_site = float(ports["rs_annual"].mean())
        # Filter to plausible Rs range (matches build_target.py: 50–4500)
        if not (50.0 <= rs_site <= 4500.0):
            n_no_qual_port += 1
            continue

        site_rows.append({
            "site_id": f"cosore_{ds.name}",
            "source": "cosore",
            "longitude": lon,
            "latitude": lat,
            "rs_annual": rs_site,
            "n_ports_qualifying": len(ports),
            "site_name": meta.get("CSR_SITE_NAME", ""),
            "igbp": meta.get("CSR_IGBP", ""),
        })
        n_ok += 1

    out = pd.DataFrame(site_rows)
    out_csv = OUT_DIR / "cosore_annual.csv"
    out.to_csv(out_csv, index=False)
    print(f"\nProcessed: {n_ok} sites with annual estimate")
    print(f"  skipped (no/bad metadata):     {n_skip_meta}")
    print(f"  skipped (RDS unreadable):      {n_skip_data}")
    print(f"  skipped (no qualifying port):  {n_no_qual_port}")
    print(f"\nWrote {out_csv}")

    if len(out):
        print(f"\nSummary:")
        print(f"  rs_annual: median={out['rs_annual'].median():.0f}  "
              f"mean={out['rs_annual'].mean():.0f}  "
              f"min={out['rs_annual'].min():.0f}  max={out['rs_annual'].max():.0f}")
        print(f"  IGBP types: {dict(out['igbp'].value_counts().head(8))}")
        # Region breakdown
        asia = out.query("25 <= longitude <= 180 and -10 <= latitude <= 80")
        us   = out.query("-125 <= longitude <= -66 and 24 <= latitude <= 50")
        print(f"  Asia: {len(asia)} sites,  US: {len(us)} sites,  "
              f"Other: {len(out) - len(asia) - len(us)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
