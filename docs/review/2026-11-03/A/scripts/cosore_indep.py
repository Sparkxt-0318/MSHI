"""Independent recomputation of the COSORE analysis rule (D-C1-6, D-P2-1) from the raw COSORE files
(read-only), compared with data/derived/cosore_annual_analysis.csv and the port table in
results/cosore_annual_analysis.json. Also: duplicates, local-time days (CSR_TIMEZONE) vs UTC days,
multi-year / Dec-Jan / leap-year structure of the kept ports."""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import rdata

REPO = Path("/home/user/MSHI")
DS = REPO / "data/raw/cosore/02f32e8e/inst/extdata/datasets"
FACTOR = 12.011 * 31536000 / 1e6
CLIP = (-2.0, 50.0)


def parse_desc(p):
    out = {}
    for line in p.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, _, v = s.partition(":")
        out[k.strip()] = v.strip()
    return out


def split_csv_line(line):
    """Char-level split on commas outside double quotes; whitespace (tabs, spaces) and quotes stripped."""
    fields, cur, q = [], [], False
    for ch in line:
        if ch == '"':
            q = not q
            continue
        if ch == "," and not q:
            fields.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    fields.append("".join(cur).strip())
    return fields


def ports_txt(p):
    if not p.exists():
        return {}
    lines = [ln for ln in p.read_text(errors="replace").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return {}
    hdr = split_csv_line(lines[0])
    out = {}
    for ln in lines[1:]:
        f = split_csv_line(ln)
        f += [""] * (len(hdr) - len(f))
        r = dict(zip(hdr, f))
        try:
            out[int(float(r["CSR_PORT"]))] = r
        except (KeyError, ValueError):
            print("   unparseable port row", p.parent.name, r.get("CSR_PORT"))
    return out


def per_port(g, day_col):
    days = g[day_col].drop_duplicates()
    months = pd.DatetimeIndex(days).month
    per_month = pd.Series(months).value_counts().reindex(range(1, 13), fill_value=0)
    fc = g.CSR_FLUX_CO2.clip(*CLIP)
    daily = fc.groupby(g[day_col]).mean()
    mon = daily.groupby(pd.DatetimeIndex(daily.index).month).mean()
    return dict(n_days=int(len(days)), span=int((days.max() - days.min()).days), min_dpm=int(per_month.min()),
                annual=float(mon.mean() * FACTOR) if len(mon) == 12 else None, obs=float(fc.mean() * FACTOR),
                years=sorted(set(pd.DatetimeIndex(days).year)))


def main():
    res = json.loads((REPO / "results/cosore_annual_analysis.json").read_text())
    committed_ports = pd.DataFrame(res["ports"]).set_index(["dataset", "port"])
    csv = pd.read_csv(REPO / "data/derived/cosore_annual_analysis.csv").set_index("site_id")
    rows, site_rows = [], []
    for ds in sorted(d for d in DS.iterdir() if d.is_dir() and not d.name.startswith("TEST")):
        rds = ds / "data" / "data.RDS"
        if not rds.exists():
            continue
        meta = parse_desc(ds / "DESCRIPTION.txt")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = rdata.parser.parse_file(rds)
            df = rdata.conversion.convert(parsed)
        if not isinstance(df, pd.DataFrame) or not {"CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"} <= set(df.columns):
            print(ds.name, "unusable", type(df))
            continue
        ts = df.CSR_TIMESTAMP_BEGIN
        d = df[["CSR_PORT", "CSR_TIMESTAMP_BEGIN", "CSR_FLUX_CO2"]].dropna().copy()
        d["t_utc"] = pd.to_datetime(d.CSR_TIMESTAMP_BEGIN.astype(float), unit="s", utc=True)
        tzname = meta.get("CSR_TIMEZONE") or meta.get("CSR_TIMESTAMP_TZ") or "UTC"
        try:
            d["t_loc"] = d.t_utc.dt.tz_convert(tzname)
        except Exception as e:  # noqa: BLE001
            print(ds.name, "tz error", tzname, e)
            d["t_loc"] = d.t_utc
        d["day_utc"] = d.t_utc.dt.tz_localize(None).dt.normalize()
        d["day_loc"] = d.t_loc.dt.tz_localize(None).dt.normalize()
        ports = ports_txt(ds / "PORTS.txt")
        ndup = int(d.duplicated(["CSR_PORT", "CSR_TIMESTAMP_BEGIN"]).sum())
        kept_vals = []
        for port, g in d.groupby("CSR_PORT"):
            m = ports.get(int(port), ports.get(0))
            u = per_port(g, "day_utc")
            lo = per_port(g, "day_loc")
            keep_meta = m is not None and m.get("CSR_MSMT_VAR") == "Rs" and m.get("CSR_TREATMENT") == "None"
            ku = keep_meta and u["n_days"] >= 150 and u["span"] >= 180 and u["min_dpm"] >= 5
            kl = keep_meta and lo["n_days"] >= 150 and lo["span"] >= 180 and lo["min_dpm"] >= 5
            gdup = int(g.duplicated(["CSR_TIMESTAMP_BEGIN"]).sum())
            rows.append(dict(dataset=ds.name, port=int(port), tz=tzname, kept_utc=ku, kept_local=kl,
                             n_days_utc=u["n_days"], n_days_loc=lo["n_days"], min_dpm_utc=u["min_dpm"],
                             min_dpm_loc=lo["min_dpm"], annual_utc=u["annual"], annual_loc=lo["annual"],
                             obs=u["obs"], years=u["years"], n_dup_ts=gdup, n=len(g)))
            if ku:
                kept_vals.append((u["annual"], u["obs"]))
        if kept_vals:
            a = np.mean([x[0] for x in kept_vals])
            site_rows.append(dict(site_id=f"cosore_{ds.name}", rs=a, obs=np.mean([x[1] for x in kept_vals]),
                                  n_kept=len(kept_vals), ndup_dataset=ndup, ts_dtype=str(ts.dtype)))
    P = pd.DataFrame(rows)
    S = pd.DataFrame(site_rows).set_index("site_id")
    P.to_csv(Path(sys.argv[1]) / "cosore_indep_ports.csv", index=False)
    # --- compare ports with the committed port table
    m = P.set_index(["dataset", "port"]).join(committed_ports, how="outer", rsuffix="_c")
    print("ports: independent", len(P), "committed", len(committed_ports), "joined", len(m))
    print("kept mismatches (UTC days):", int((m.kept_utc != m.kept).sum()))
    print("n_days mismatches:", int((m.n_days_utc != m.n_days).sum()), " min_dpm mismatches:",
          int((m.min_dpm_utc != m.min_days_in_a_month).sum()))
    both = m.annual_utc.notna() & m.rs_annual.notna()
    print("annual value max |diff| (kept/any port):", float((m.annual_utc[both] - m.rs_annual[both]).abs().max()))
    print("obs mean max |diff|:", float((m.obs - m.rs_annual_obs_mean).abs().max()))
    # --- sites
    j = S.join(csv, how="outer")
    print("sites: independent", len(S), "csv", len(csv))
    print("site rs max |diff|:", float((j.rs - j.rs_annual).abs().max()), " obs max |diff|:",
          float((j.obs - j.rs_annual_obs_mean).abs().max()))
    print("site n_ports mismatch:", int((j.n_kept != j.n_ports_qualifying).sum()))
    print("timestamp dtypes:", S.ts_dtype.value_counts().to_dict())
    # --- duplicates, local days
    k = P[P.kept_utc]
    print("kept ports with duplicated timestamps:", int((k.n_dup_ts > 0).sum()), "rows:", int(k.n_dup_ts.sum()))
    print(k[k.n_dup_ts > 0][["dataset", "port", "n", "n_dup_ts"]].to_string())
    print("ports whose kept status differs, UTC vs local days:")
    print(P[P.kept_utc != P.kept_local][["dataset", "port", "tz", "n_days_utc", "n_days_loc", "min_dpm_utc",
                                         "min_dpm_loc", "kept_utc", "kept_local"]].to_string())
    kk = P[P.kept_utc & P.kept_local]
    rel = (kk.annual_loc / kk.annual_utc - 1).abs()
    print("kept ports: annual (local days) vs (UTC days): max rel diff %.4g, median %.4g" % (rel.max(), rel.median()))
    print(kk.assign(rel=rel).sort_values("rel", ascending=False).head(8)[["dataset", "port", "tz", "annual_utc",
                                                                          "annual_loc", "rel"]].to_string())
    print("kept ports by number of years with data:", k.years.map(len).value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
