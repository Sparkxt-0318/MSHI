"""Synthetic feature tables on the real v3 QC-site geometry (lat, lon, continent only).
Every covariate and the target log_rs are SYNTHETIC; the real log_rs column is dropped."""
import sys
import numpy as np, pandas as pd

OUT = sys.argv[1]
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


# S1: linear in bio01 + ln(bio12) -> OLS-TP expected
d, rng = covariates(11)
d["log_rs"] = 5.6 + 0.035 * d.bio01 + 0.22 * np.log(d.bio12) + rng.normal(0, 0.45, len(d))
d.loc[d.index[rng.choice(len(d), 6, replace=False)], "log_rs"] = np.nan
d.to_parquet(f"{OUT}/S1_ols.parquet", index=False)

# S2: non-linear, uses soil + MODIS -> an ML learner on a big set expected
d, rng = covariates(22)
z = ((d.soc - 30) / 15).fillna(0)
d["log_rs"] = (6.0 + 0.6 * np.tanh(z * 2) * np.sign(d.bio01 - 8) + 0.3 * ((d.npp.fillna(500) - 500) / 200) ** 2
               - 0.4 * (d.clay.fillna(22) > 28) + 0.25 * np.cos(d.lst_diurnal_range.fillna(11) / 2)
               + rng.normal(0, 0.12, len(d)))
d.loc[d.index[rng.choice(len(d), 4, replace=False)], "log_rs"] = np.nan
d.to_parquet(f"{OUT}/S2_ml.parquet", index=False)

# S3: thresholds / interactions on many C8 variables -> try to get RF selected
d, rng = covariates(33)
s = ((d.bio04 > 900).astype(float) + (d.bio15 > 45) + (d.bio14 > 20) + (d.bio06 > 0) + (d.bio17 > 90)
     + (d.sand.fillna(40) > 45) + (d.phh2o > 6.3))
d["log_rs"] = 5.5 + 0.35 * s * (d.bdod > 1.3) + 0.25 * s * (d.cec > 18) + rng.normal(0, 0.15, len(d))
d.to_parquet(f"{OUT}/S3_rf.parquet", index=False)
print("written", OUT)
