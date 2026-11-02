import sys, numpy as np, pandas as pd
D = sys.argv[1]
pd.set_option("display.width", 250)
pm = pd.read_csv(f"{D}/cosore_port_monthly.csv")
st = pd.read_csv(f"{D}/cosore_annual.csv", keep_default_na=False); st["ds"] = st.site_id.str.replace("cosore_", "", regex=False)
M = [f"m{m:02d}" for m in range(1, 13)]
pm = pm.merge(st[["ds", "latitude", "igbp", "rs_annual"]], on="ds")
pm["nm"] = pm[M].notna().sum(1)
full = pm[(pm.nm == 12) & (pm.latitude.abs() > 35)]
print(f"full-year ports at |lat|>35: {len(full)} ports in {full.ds.nunique()} datasets")
# expected inflation for a growing-season-only window (the commonest partial pattern Apr-Nov, May-Nov)
for name, months in [("Apr-Nov", range(4, 12)), ("May-Nov", range(5, 12)), ("Apr-Dec", range(4, 13)), ("Mar-Nov", range(3, 12))]:
    cols = [f"m{m:02d}" for m in months]
    ratio = full[cols].mean(1) / full[M].mean(1)
    # per-dataset median of port ratios, then median across datasets
    rd = ratio.groupby(full.ds).median()
    print(f"  mean(flux over {name}) / mean(12 months): median over datasets {rd.median():.2f}  IQR [{rd.quantile(.25):.2f}, {rd.quantile(.75):.2f}]  n_ds={len(rd)}")
# per partial site: which months present (site-level union over qualifying ports) and the implied inflation using full-year ports' climatology
site_months = pm.groupby("ds")[M].apply(lambda x: x.notna().any())
rows = []
for ds, mk in site_months.iterrows():
    if mk.all(): continue
    cols = [c for c in M if mk[c]]
    lat = st.set_index("ds").latitude[ds]
    ref = full if abs(lat) > 35 else pm[(pm.nm == 12) & (pm.latitude.abs() <= 35)]
    ratio = (ref[cols].mean(1) / ref[M].mean(1)).groupby(ref.ds).median().median()
    rows.append(dict(ds=ds, lat=round(lat, 2), months="".join("x" if mk[c] else "." for c in M), rs_annual=round(st.set_index("ds").rs_annual[ds]), implied_inflation=round(ratio, 2)))
P = pd.DataFrame(rows).sort_values("implied_inflation", ascending=False)
print(f"\nsites with at least one calendar month missing in all qualifying ports: {len(P)}")
print(P.to_string(index=False))
