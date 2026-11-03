"""Area D check 1: us_r2 helpers on the REAL analysis site and record tables (no features needed).

- single_record() on both variants: does it accept the real tables (n_rec / mean log Rs within MEAN_ATOL)?
- counts claimed in docs/DECISIONS.md D-P2-11: US bounding box composition (USA 175, Canada 15, Mexico 1),
  COSORE ties (3 sites per variant), no training/test overlap, 30 geographic-Europe QC sites in the Asia box.
Reads data/derived (read-only); writes nothing to the repository.
"""
import sys
sys.path.insert(0, "/home/user/MSHI")
import copy
import numpy as np
import pandas as pd

from mshi.config import load_config, Config
from mshi.analysis import us_r2 as U

cfg = load_config()
S = U.Settings.from_cfg(cfg)
print("settings:", S.learners, S.train_continent, S.test_continent, S.asia_box, S.us_box, S.seed_spread, S.min_sites)
rec = pd.read_parquet("/home/user/MSHI/data/derived/records_analysis.parquet")
print("records:", rec.shape, rec.src.value_counts().to_dict())
print("cosore rec_ids (first 5):", sorted(rec[rec.src == "cosore"].rec_id)[:5])
trains, tests = U.regions(S)
for v in ("qc", "repo"):
    st = pd.read_parquet(f"/home/user/MSHI/data/derived/sites_analysis_{v}.parquet")
    d = st.sort_values("site_id", kind="mergesort").reset_index(drop=True)
    try:
        sr, info = U.single_record(rec, d, v, "log_rs")
        print(f"[{v}] single_record OK:", info)
    except Exception as e:  # noqa
        print(f"[{v}] single_record RAISED: {type(e).__name__}: {e}")
        agg = rec[rec[f"site_id_{v}"].notna()].groupby(f"site_id_{v}").log_rs.agg(["size", "mean"])
        chk = d.set_index("site_id")[["n_rec", "log_rs"]].join(agg)
        print("   max |mean diff|:", float((chk["mean"] - chk.log_rs).abs().max()))
    # max abs diff of site mean vs records mean
    agg = rec[rec[f"site_id_{v}"].notna()].groupby(f"site_id_{v}").log_rs.agg(["size", "mean"])
    chk = d.set_index("site_id")[["n_rec", "log_rs"]].join(agg)
    print(f"[{v}] max |site log_rs - mean(records)| = {float((chk['mean'] - chk.log_rs).abs().max()):.3g}; "
          f"n_rec mismatches = {int((chk['size'] != chk.n_rec).sum())}")
    # COSORE ties
    r = rec[rec[f"site_id_{v}"].notna()]
    nc = r[r.src == "cosore"].groupby(f"site_id_{v}").size()
    print(f"[{v}] sites with >1 COSORE record: {int((nc > 1).sum())}: {list(nc[nc > 1].index)}")
    # composition of regions
    comp = U.composition(d, trains, tests)
    for name, e in comp.items():
        print(f"[{v}] region {name!r}: n={e['n']} by_continent_geo={e['by_continent_geo']}"
              + (f" by_country={e.get('by_country')}" if 'by_country' in e else "")
              + (f" rel={e.get('relative_to_box')}" if 'relative_to_box' in e else ""))
    ov = U.overlaps(d, trains, tests)
    print(f"[{v}] overlaps:", [(o['train'], o['test'], o['n'], o['examples']) for o in ov if o['n']])
    # Asia box geographic Europe
    abox = trains[1].mask(d)
    print(f"[{v}] Asia box by continent_geo:", d[abox].continent_geo.value_counts().to_dict())
    # sites with continent_geo missing
    print(f"[{v}] continent_geo missing:", int(d.continent_geo.isna().sum()))
    # NA sites near the antimeridian / Asia box west Aleutians
    na = d[d.continent_geo.eq("North America")]
    print(f"[{v}] NA sites with lon > 0:", na[na.lon > 0][["site_id", "lon", "lat", "country"]].values.tolist())
    asia = d[d.continent_geo.eq("Asia")]
    print(f"[{v}] Asia sites outside the Asia box:", int((~U.in_box(asia.lon, asia.lat, S.asia_box)).sum()),
          asia[~U.in_box(asia.lon, asia.lat, S.asia_box)][["site_id", "lon", "lat", "country"]].values.tolist()[:10])
