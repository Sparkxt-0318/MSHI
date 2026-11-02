import sys, numpy as np, pandas as pd
V = sys.argv[1]; K = 12.011 * 31_536_000.0 / 1e6
p = pd.read_csv(f"{V}/out/cosore/ports_diag.csv", keep_default_na=False, na_values=[""]); p = p[p.ds != "d20200331_PEICHL"]
mo = pd.read_csv(f"{V}/out/cosore/ports_monthly.csv")
c = pd.read_csv(f"{V}/out/cosore/cosore_annual.csv"); c["ds"] = c.site_id.str.replace("cosore_", "")
site = p.groupby("ds").agg(max_months=("n_months", "max"), min_months=("n_months", "min"), n_ports=("port", "size"),
                           clipm=("clip_mean", "mean"), drop=("drop_mean", "mean"), monthbal=("month_bal_mean", "mean"),
                           frac_hi=("frac_hi", "max"), frac_lo=("frac_lo", "max"), raw=("raw_mean", "mean"), years=("years", "max"))
site = site.join(c.set_index("ds")[["latitude", "longitude", "rs_annual"]])
full = site.max_months == 12
print(f"sites: {len(site)}; with no qualifying port covering all 12 calendar months: {(~full).sum()}")
# months covered by partial sites
for ds, g in mo[mo.ds.isin(site.index[~full])].groupby("ds"):
    print(f"  {ds:34s} lat {site.loc[ds,'latitude']:7.2f} months(pooled over ports) {sorted(g.month.unique())}")
# season-window ratios from full-year ports (temperate/boreal = |lat| >= 23.5), month climatology per port, averaged per dataset
fy = mo.merge(p[p.n_months == 12][["ds", "port"]], on=["ds", "port"])
fy = fy.merge(site[["latitude"]], left_on="ds", right_index=True)
tb = fy[fy.latitude.abs() >= 23.5]
def ratio(g, months):
    return g[g.month.isin(months)]["mean"].mean() / g["mean"].mean()
r = tb.groupby(["ds", "port"]).apply(lambda g: pd.Series({"AprNov": ratio(g, range(4, 12)), "MayNov": ratio(g, range(5, 12))}), include_groups=False)
rd = r.groupby("ds").mean()
print(f"\nfull-year temperate/boreal datasets: {len(rd)}; Apr-Nov / 12-month ratio median {rd.AprNov.median():.3f} IQR [{rd.AprNov.quantile(.25):.3f}, {rd.AprNov.quantile(.75):.3f}]; May-Nov median {rd.MayNov.median():.3f}")
# obs-weighted (as handoff) vs month-balanced, full-year datasets
fb = site[full]; ratio_ow = fb["clipm"] / fb.monthbal
print(f"full-year datasets {len(fb)}: obs-weighted/month-balanced median {ratio_ow.median():.3f}; >1.10: {(ratio_ow > 1.10).sum()}; <0.90: {(ratio_ow < 0.90).sum()}")
print("partial-year datasets obs-weighted/month-balanced:", (site[~full]["clipm"] / site[~full].monthbal).round(3).describe()[["count","50%","min","max"]].to_dict())
# clipping vs dropping
site["clip_vs_drop_log"] = np.log(site["clipm"] / site["drop"])
print("\nclip vs drop (log), largest:"); print(site.sort_values("clip_vs_drop_log", key=abs, ascending=False)[["raw", "clipm", "drop", "frac_hi", "frac_lo", "clip_vs_drop_log"]].head(6).round(3).to_string())
print("PANG g C: clip", round(site.loc["d20191214_PANG","clipm"]*K,1), "drop", round(site.loc["d20191214_PANG","drop"]*K,1))
print("multi-year datasets (max years per port >1):", int((site.years > 1).sum()))
site.to_csv(f"{V}/out/cosore/site_season.csv")
