"""Seam: europe_geo_sensitivity labels each LOCKED site by geographic_continent at the site's mean point, while
build_sites_analysis labels a site by the mode of its records' continent_geo. Do the two rules ever differ on the
locked QC/repo tables (and on the analysis tables)? Reads data/derived and data/raw/naturalearth (read-only).
"""
import sys
sys.path.insert(0, "/home/user/MSHI")
import numpy as np
import pandas as pd

from mshi.config import load_config
from mshi.geo import geographic_continent, subunits

cfg = load_config()
su = subunits(cfg)
rec = pd.read_parquet("/home/user/MSHI/data/derived/records_v3.parquet")
g = geographic_continent(cfg, rec.lon.values, rec.lat.values, su)
rec = rec.assign(continent_geo=g.continent_geo.values)


def mode(x):
    x = x.dropna()
    return x.mode().iat[0] if len(x) else np.nan


for v in ("qc", "repo"):
    st = pd.read_parquet(f"/home/user/MSHI/data/derived/sites_v3_{v}.parquet")
    by_point = geographic_continent(cfg, st.lon.values, st.lat.values, su).continent_geo.values
    by_rec = st.site_id.map(rec[rec[f"site_id_{v}"].notna()].groupby(f"site_id_{v}").continent_geo.agg(mode))
    diff = st[(pd.Series(by_point, index=st.index).fillna("NA!") != by_rec.fillna("NA!"))]
    print(f"locked {v}: sites {len(st)}; point rule vs record-mode rule differ at {len(diff)} sites")
    for i, r in diff.iterrows():
        print("   ", r.site_id, round(r.lat, 4), round(r.lon, 4), r.country, "point:", by_point[i], "records:",
              by_rec[i], "locked continent:", r.continent)
    eu = st.continent.eq("Europe")
    print(f"locked {v}: locked-Europe sites {int(eu.sum())}; geographic Europe by point {int((by_point[eu] == 'Europe').sum())}"
          f", by record mode {int((by_rec[eu] == 'Europe').sum())}")
ra = pd.read_parquet("/home/user/MSHI/data/derived/records_analysis.parquet")
for v in ("qc", "repo"):
    st = pd.read_parquet(f"/home/user/MSHI/data/derived/sites_analysis_{v}.parquet")
    by_point = geographic_continent(cfg, st.lon.values, st.lat.values, su).continent_geo.values
    d = int((pd.Series(by_point).fillna("NA!").values != st.continent_geo.fillna("NA!").values).sum())
    print(f"analysis {v}: site continent_geo (record mode) vs point rule at the site mean: {d} differ")
