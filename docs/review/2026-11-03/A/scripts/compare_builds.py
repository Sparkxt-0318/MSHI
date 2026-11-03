"""The analysis build vs the locked build (D-P2-2, D-P2-3, D-P2-12): records, flags, sites, continents;
records/sites whose records disagree on continent_geo; the mode tie-break."""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/MSHI")
from mshi.config import load_config  # noqa: E402
from mshi.geo import geographic_continent, subunits  # noqa: E402

cfg = load_config()
D = "/home/user/MSHI/data/derived/"
L = pd.read_parquet(D + "records_v3.parquet")
A = pd.read_parquet(D + "records_analysis.parquet")
print("records locked", len(L), "analysis", len(A))
only_l, only_a = set(L.rec_id) - set(A.rec_id), set(A.rec_id) - set(L.rec_id)
print("only locked", len(only_l), "all cosore:", all(x.startswith("cosore_") for x in only_l), "only analysis", len(only_a))
m = L.merge(A, on="rec_id", suffixes=("_l", "_a"))
for c in ["lat", "lon", "rs", "continent", "geo_country", "f_offland", "f_method", "f_quality", "f_coverage", "f_ecosys",
          "f_dup", "Country"]:
    eq = (m[f"{c}_l"].astype(str) == m[f"{c}_a"].astype(str))
    print(f"  {c:12s} equal for all common records: {bool(eq.all())}  (differ: {int((~eq).sum())})")
# COSORE records common to both: values changed (analysis rule)?
cc = m[m.rec_id.str.startswith("cosore_")]
print("common COSORE records:", len(cc), " rs changed:", int((cc.rs_l != cc.rs_a).sum()))
print(cc.assign(ratio=cc.rs_a / cc.rs_l)[["rec_id", "rs_l", "rs_a", "ratio"]].sort_values("ratio").to_string())

# sites
for tag in ("qc", "repo"):
    Ls = pd.read_parquet(D + f"sites_v3_{tag}.parquet")
    As = pd.read_parquet(D + f"sites_analysis_{tag}.parquet")
    # map by record membership
    lm = L[["rec_id", f"site_id_{tag}"]].dropna()
    am = A[["rec_id", f"site_id_{tag}"]].dropna()
    lset = lm.groupby(f"site_id_{tag}").rec_id.apply(frozenset)
    aset = am.groupby(f"site_id_{tag}").rec_id.apply(frozenset)
    same = set(lset.values) & set(aset.values)
    print(f"[{tag}] locked sites {len(Ls)}, analysis sites {len(As)}; identical record sets: {len(same)}")
    print(f"   locked sites whose record set is not in analysis: {len(set(lset.values) - same)}; analysis-only sets: "
          f"{len(set(aset.values) - same)}")
    for s in sorted(set(aset.values) - same, key=lambda x: sorted(x)[0]):
        print("     analysis-only site record set:", sorted(s)[:6], "..." if len(s) > 6 else "")
    for s in sorted(set(lset.values) - same, key=lambda x: sorted(x)[0]):
        print("     locked-only site record set:", sorted(s)[:6], "..." if len(s) > 6 else "")
    # records disagreeing on continent_geo within a site
    g = am.merge(A[["rec_id", "continent_geo", "geo_subunit", "lat", "lon"]], on="rec_id")
    nun = g.groupby(f"site_id_{tag}").continent_geo.nunique()
    multi = nun[nun > 1].index
    print(f"   sites with records on >1 continent_geo: {len(multi)}")
    for s in multi:
        x = g[g[f"site_id_{tag}"] == s]
        print("     ", s, x.continent_geo.value_counts().to_dict(), x.geo_subunit.value_counts().to_dict(),
              "-> site:", As.set_index("site_id").loc[s, ["continent_geo", "geo_subunit", "lat", "lon"]].to_dict())
    nsu = g.groupby(f"site_id_{tag}").geo_subunit.nunique()
    print(f"   sites with records in >1 subunit: {int((nsu > 1).sum())}")
    for s in nsu[nsu > 1].index:
        x = g[g[f"site_id_{tag}"] == s]
        print("     ", s, x.geo_subunit.value_counts().to_dict(), "-> site:",
              As.set_index("site_id").loc[s, ["continent_geo", "geo_subunit"]].to_dict())
    # continent_geo of the site centroid vs the record mode
    c = geographic_continent(cfg, As.lon.values, As.lat.values, subunits(cfg))
    d = (c.continent_geo.values != As.continent_geo.values)
    print(f"   sites whose centroid continent_geo differs from the record mode: {int(d.sum())}")
    if d.any():
        print(As.loc[d, ["site_id", "lat", "lon", "continent_geo", "geo_subunit"]].assign(centroid=c.continent_geo.values[d],
              centroid_subunit=c.geo_subunit.values[d]).to_string())

# locked QC table: continent_geo by site centroid (as europe_geo does on features_v3_qc) and by record mode
Ls = pd.read_parquet(D + "sites_v3_qc.parquet")
c = geographic_continent(cfg, Ls.lon.values, Ls.lat.values, subunits(cfg))
Ls = Ls.assign(cg=c.continent_geo.values, su=c.geo_subunit.values)
ch = Ls[Ls.continent != Ls.cg]
print("locked QC sites whose centroid continent_geo != locked continent:", len(ch))
print(ch[["site_id", "lat", "lon", "country", "continent", "cg", "su"]].to_string())
print("geographic Europe in the locked QC set (centroid):", int((Ls.cg == "Europe").sum()),
      "; locked Europe:", int((Ls.continent == "Europe").sum()))
g = L[["rec_id", "site_id_qc"]].dropna().merge(A[["rec_id", "continent_geo"]], on="rec_id", how="left")
print("  locked QC records without an analysis continent_geo (dropped COSORE):", int(g.continent_geo.isna().sum()))
