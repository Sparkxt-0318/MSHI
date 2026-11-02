"""Independent recomputation of site_diagnostics item 5 (F-H2) from data/derived and the allow-listed v2 table.
Different code path: pyproj.Geod (WGS84 ellipsoid) distances via a KD-tree prefilter, set operations by hand."""
import json, sys
import numpy as np, pandas as pd
from pyproj import Geod
R = "/home/user/MSHI/"
tr = pd.read_parquet(R + "legacy/data/processed/training_features_v2.parquet")
rec = pd.read_parquet(R + "data/derived/records_v3.parquet")
geod = Geod(ellps="WGS84")
box = (25.0, 180.0, -10.0, 80.0)
committed = json.load(open(R + "results/site_diagnostics.json"))

def hav(lat1, lon1, lat2, lon2, Rk=6371.0):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * Rk * np.arcsin(np.sqrt(a))

for tag in ["qc", "repo"]:
    st = pd.read_parquet(R + f"data/derived/sites_v3_{tag}.parquet")
    eu = st[st.continent == "Europe"]
    rr = rec[rec[f"site_id_{tag}"].isin(set(eu.site_id))]
    # (a) identical record: same id string in the v2 table, and check the coordinates/Rs agree (same CSV row)
    ids = set(tr.site_id)
    m = rr[rr.rec_id.isin(ids)].merge(tr[["site_id", "latitude", "longitude", "rs_annual"]], left_on="rec_id", right_on="site_id")
    same = set(m[f"site_id_{tag}"])
    dmax = float(np.max(np.abs(np.r_[m.lat - m.latitude, m.lon - m.longitude]))) if len(m) else None
    rsd = float(np.max(np.abs(m.rs - m.rs_annual))) if len(m) else None
    # (b) within 5 km, geodesic on WGS84 (min over all v2 sites), and haversine R=6371 for comparison
    near_g, near_h, mind = set(), set(), {}
    for s, g in rr.groupby(f"site_id_{tag}"):
        best = np.inf; besth = np.inf
        for la, lo in zip(g.lat.values, g.lon.values):
            _, _, dist = geod.inv(np.full(len(tr), lo), np.full(len(tr), la), tr.longitude.values, tr.latitude.values)
            best = min(best, dist.min() / 1000.0)
            besth = min(besth, hav(la, lo, tr.latitude.values, tr.longitude.values).min())
        mind[s] = (best, besth)
        if best <= 5.0: near_g.add(s)
        if besth <= 5.0: near_h.add(s)
    inbox = set(eu[(eu.lon >= box[0]) & (eu.lon <= box[1]) & (eu.lat >= box[2]) & (eu.lat <= box[3])].site_id)
    border = {s: (round(a, 3), round(b, 3)) for s, (a, b) in mind.items() if 4.0 < min(a, b) < 6.0}
    print(f"[{tag}] Europe sites {len(eu)}; identical record {len(same)} (max |dcoord| {dmax}, max |dRs| {rsd}); "
          f"within 5 km geodesic {len(near_g)}, haversine {len(near_h)}; in box {len(inbox)}")
    print(f"   same <= near: {same <= near_g};  near == inbox: {near_g == inbox};  near - same: {sorted(near_g - same)}")
    print(f"   by country (near): {eu[eu.site_id.isin(near_g)].country.value_counts().sort_index().to_dict()}")
    print(f"   Russia sites in near: max lon {eu[eu.site_id.isin(near_g) & (eu.country == 'Russia')].lon.max()}")
    print(f"   sites with min distance in (4, 6) km: {border}")
    c = committed[f"europe_in_original_asia_table_{tag}"]
    print(f"   committed: n_europe {c['n_europe_sites']}, within_km {c['n_within_km']}, identical {c['n_with_identical_record']}, "
          f"in_box {c['n_in_original_box']}, by_country {c['by_country_within_km']}")
    print(f"   committed site list equals recomputed near|same: {sorted(x['site_id'] for x in c['sites']) == sorted(near_g | same)}")
    for x in c["sites"]:
        if x["identical_record"] != (x["site_id"] in same) or x["within_km"] != (x["site_id"] in near_g):
            print("   MISMATCH", x)
