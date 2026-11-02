import sys, numpy as np, pandas as pd
D = sys.argv[1]
pp = pd.read_csv(f"{D}/cosore_ports_diag.csv", keep_default_na=False, na_values={"mean_clip":[""],"mean_raw":[""],"mean_drop":[""]}); st = pd.read_csv(f"{D}/cosore_annual.csv", keep_default_na=False)
K = 12.011 * 31_536_000.0 / 1e6
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
st["ds"] = st.site_id.str.replace("cosore_", "", regex=False)
q = pp[pp.qual & pp.ds.isin(st.ds)].copy()
print("qualifying ports in the 66 sites:", len(q))
q["msmt_var"] = q.msmt_var.replace("", "?"); q["treatment"] = q.treatment.replace("", "?")
print(q.groupby(["msmt_var"]).size()); print(q.groupby(["treatment"]).size())
bad = q[(q.msmt_var != "Rs") | (~q.treatment.isin(["None"]))]
print("\nnon-Rs or treated qualifying ports:", len(bad), "in", bad.ds.nunique(), "datasets")
print(bad.groupby(["ds", "msmt_var", "treatment"]).size().to_string())
# site estimate restricted to Rs + None
def site_est(g): return g.mean_clip.mean() * K
full = q.groupby("ds").apply(site_est, include_groups=False).rename("rs_all")
ctl = q[(q.msmt_var == "Rs") & (q.treatment == "None")].groupby("ds").apply(site_est, include_groups=False).rename("rs_ctl")
cmp = pd.concat([full, ctl], axis=1)
cmp["dlog"] = np.log(cmp.rs_all) - np.log(cmp.rs_ctl)
chg = cmp[(cmp.dlog.abs() > 1e-9) | cmp.rs_ctl.isna()]
print("\nsites whose estimate changes if restricted to Rs/None ports (rs_ctl NaN = no Rs/None qualifying port):")
print(chg.round(3).to_string())
print("\n== seasonal coverage of qualifying ports (all 66 sites)")
print("ports with <12 calendar months:", (q.n_months < 12).sum(), "/", len(q), "; with <=9 months:", (q.n_months <= 9).sum())
print("span_days distribution:", q.span_days.describe().round(0).to_dict())
q["ratio_obs_vs_daybal"] = q.mean_clip / q.mean_daybal
q["ratio_obs_vs_monthbal"] = q.mean_clip / q.mean_monthbal_present
print("ratio obs-weighted/day-balanced mean:", q.ratio_obs_vs_daybal.describe().round(3).to_dict())
print("ratio obs-weighted/month-balanced mean:", q.ratio_obs_vs_monthbal.describe().round(3).to_dict())
site_m = q.groupby("ds").agg(n_months_min=("n_months", "min"), n_months_max=("n_months", "max"), span=("span_days", "max"),
                            months=("months_present", "first"), first=("first", "min"), last=("last", "max"))
print("\nsites whose qualifying ports all cover <12 months:", (site_m.n_months_max < 12).sum())
print(site_m[site_m.n_months_max < 12].join(st.set_index("ds")[["igbp", "rs_annual", "latitude", "longitude"]]).to_string())
print("\n== clipping")
print("ports with any flux >50:", (q.frac_hi > 0).sum(), " any < -2:", (q.frac_lo > 0).sum())
q["clip_vs_drop"] = q.mean_clip / q.mean_drop
print("clip/drop ratio:", q.clip_vs_drop.describe().round(4).to_dict())
print(q.sort_values("frac_hi", ascending=False)[["ds", "port", "n", "frac_hi", "frac_lo", "mean_raw", "mean_clip", "mean_drop"]].head(8).round(4).to_string())
print("\n== IGBP of the 66")
print(st.igbp.value_counts().to_string())
print(st[st.igbp.str.upper().isin(["WET", "WETLAND", "URB"])][["site_id", "igbp", "latitude", "longitude", "rs_annual"]].to_string())
