"""Synthetic clean-test tables for the RF re-check (verifier's own copy).
Only lat/lon/continent/site_id of the committed QC site table are used; covariates and target are synthetic.
V2 reproduces the reviewer's V2 formula (seed 202) so the leaf at issue can be compared; W3 is my own table
(different seed and structure, RF expected to be competitive).  usage: rf_synth.py OUTDIR"""
import sys
import numpy as np
import pandas as pd
OUT = sys.argv[1]
base = pd.read_parquet(sys.argv[2])[["site_id", "lat", "lon", "continent"]].copy()

def covs(seed):
    r = np.random.default_rng(seed)
    d = base.copy(); n = len(d); lat, lon = d.lat.values, d.lon.values
    d["bio01"] = 25 - 0.4 * np.abs(lat) + r.normal(0, 3, n)
    d["bio04"] = 300 + 10 * np.abs(lat) + r.normal(0, 80, n)
    d["bio05"] = d.bio01 + 9 + r.normal(0, 2.5, n)
    d["bio06"] = d.bio01 - 11 + r.normal(0, 3.5, n)
    d["bio12"] = np.exp(6.8 + 0.5 * np.cos(np.radians(lon * 1.3)) + r.normal(0, 0.5, n))
    d["bio14"] = np.abs(d.bio12 / 35 + r.normal(0, 6, n))
    d["bio15"] = 50 + r.normal(0, 20, n)
    d["bio17"] = np.abs(d.bio12 / 8 + r.normal(0, 25, n))
    for c, mu, sd in [("soc", 25, 12), ("nitrogen", 2.2, .9), ("phh2o", 6.0, 1.1), ("clay", 20, 8),
                      ("sand", 42, 14), ("silt", 33, 9), ("bdod", 1.35, .14), ("cec", 16, 6)]:
        d[c] = mu + sd * r.normal(0, 1, n)
    d["npp"] = 350 + 22 * d.bio01 + r.normal(0, 100, n)
    d["lst_day"] = d.bio01 + 7 + r.normal(0, 2.2, n)
    d["lst_night"] = d.bio01 - 6 + r.normal(0, 2.2, n)
    d["lst_diurnal_range"] = d.lst_day - d.lst_night
    for c, frac in [("npp", .05), ("lst_night", .04), ("soc", .03), ("bio14", .005)]:
        idx = r.choice(n, int(frac * n), replace=False)
        d.loc[d.index[idx], c] = np.nan
        if c == "lst_night":
            d.loc[d.index[idx], "lst_diurnal_range"] = np.nan
    return d, r

d, r = covs(202)
z = lambda c: (d[c] - d[c].mean()) / d[c].std()
d["log_rs"] = (5.8 + 0.30 * np.sign(z("bio04")) * np.sign(z("bio15")) * (z("bio06") > -0.3)
               + 0.25 * (z("bio17") > 0.4) * (z("bio14") > -0.2) + 0.2 * np.tanh(3 * z("bio05"))
               + r.normal(0, 0.35, len(d)))
d.to_parquet(f"{OUT}/V2_rf.parquet", index=False)

d, r = covs(777)
z = lambda c: (d[c] - d[c].mean()) / d[c].std()
d["log_rs"] = (6.0 + 0.35 * (z("bio04") > 0.2) * (z("bio17") > -0.5) - 0.25 * (z("bio06") < -0.4) * (z("bio15") > 0)
               + 0.15 * np.tanh(2 * z("bio14")) + r.normal(0, 0.30, len(d)))
d.to_parquet(f"{OUT}/W3_rf.parquet", index=False)
print("written", OUT)
