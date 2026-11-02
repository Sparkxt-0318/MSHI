"""Synthetic feature tables on the real v3 QC-site geometry (lat, lon, continent only).
Every covariate and the target log_rs are SYNTHETIC; the real log_rs column is dropped."""
import sys
import numpy as np, pandas as pd

sites = pd.read_parquet("/home/user/MSHI/data/derived/sites_v3_qc.parquet")
base = sites[["site_id", "lat", "lon", "continent"]].copy()        # real geometry only; real log_rs NOT used


def covariates(seed):
    rng = np.random.default_rng(seed)
    d = base.copy()
    n = len(d)
    lat, lon = d.lat.values, d.lon.values
    eu = (d.continent == "Europe").values
    d["bio01"] = 28 - 0.45 * np.abs(lat) + rng.normal(0, 2.5, n) + np.where(eu, 3.0, 0.0)   # Europe shifted
    d["bio04"] = 200 + 12 * np.abs(lat) + rng.normal(0, 60, n)
    d["bio05"] = d.bio01 + 10 + rng.normal(0, 2, n)
    d["bio06"] = d.bio01 - 12 + rng.normal(0, 3, n)
    d["bio12"] = np.exp(6.6 + 0.6 * np.sin(np.radians(lon)) + rng.normal(0, 0.45, n))
    d["bio14"] = np.abs(d.bio12 / 40 + rng.normal(0, 5, n))
    d["bio15"] = 40 + rng.normal(0, 18, n)
    d["bio17"] = np.abs(d.bio12 / 9 + rng.normal(0, 20, n))
    for c, mu, sd in [("soc", 30, 15), ("nitrogen", 2.5, 1), ("phh2o", 6.2, 1), ("clay", 22, 9), ("sand", 40, 15),
                      ("silt", 35, 10), ("bdod", 1.3, .15), ("cec", 18, 7)]:
        d[c] = mu + sd * rng.normal(0, 1, n) + 0.05 * sd * lat / 10
    d["npp"] = 300 + 25 * d.bio01 + rng.normal(0, 90, n)
    d["lst_day"] = d.bio01 + 6 + rng.normal(0, 2, n)
    d["lst_night"] = d.bio01 - 5 + rng.normal(0, 2, n)
    d["lst_diurnal_range"] = d.lst_day - d.lst_night
    # missing values in several covariates (different n per candidate set)
    for c, frac in [("npp", .06), ("lst_day", .03), ("soc", .02), ("clay", .015), ("bio12", .004)]:
        idx = rng.choice(n, int(frac * n), replace=False)
        d.loc[d.index[idx], c] = np.nan
        if c == "lst_day":
            d.loc[d.index[idx], "lst_diurnal_range"] = np.nan
    return d, rng


